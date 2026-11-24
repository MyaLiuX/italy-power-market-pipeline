"""Extract one delivery day of ENTSO-E data for every active Italian bidding zone.

For each dataset, every zone is requested separately, clipped to the day's
window, converted to UTC and reshaped to a standard long table. The zones are
then stacked into one table and written as a single parquet file per dataset.

"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from entsoe import EntsoePandasClient
from entsoe.exceptions import NoMatchingDataError

from italy_power_market_pipeline.ingest.client import EntsoeRequestError, call_with_retry
from italy_power_market_pipeline.ingest.timewindow import clip_to_window, day_window_utc
from italy_power_market_pipeline.ingest.zones import active_zones

logger = logging.getLogger(__name__)


# --- Reshaping: one function per dataset ------------------------------------
# Each receives one zone's data, already clipped and converted to UTC,
# and returns a table whose first column is ts_utc.


def _prices_to_frame(raw: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"ts_utc": raw.index, "price_eur_mwh": raw.to_numpy()})


def _load_to_frame(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"ts_utc": raw.index, "load_mw": raw["Actual Load"].to_numpy()})


def _generation_to_frame(raw: pd.Series | pd.DataFrame) -> pd.DataFrame:
    """Unpivot the wide generation table to one row per (ts, type, measure).
    """
    if isinstance(raw, pd.Series):
        raw = raw.to_frame()
    if raw.columns.nlevels == 1:
        raw.columns = pd.MultiIndex.from_product([raw.columns, ["Actual Aggregated"]])

    # stack keeps NaN values as rows (reported-but-missing stays NULL) and
    # creates no row for a column that does not exist (type absent in the zone).
    long = raw.stack(level=[0, 1])
    long.index = long.index.set_names(["ts_utc", "production_type", "measure"])
    return long.rename("value_mw").reset_index()


@dataclass(frozen=True)
class DatasetSpec:
    name: str  # also the folder name under the output directory
    method: str  # EntsoePandasClient method that fetches it
    to_frame: Callable[..., pd.DataFrame]
    key: tuple[str, ...]  # columns that identify one row; must be unique


DATASETS = (
    DatasetSpec("day_ahead_prices", "query_day_ahead_prices", _prices_to_frame,
                ("zone", "ts_utc")),
    DatasetSpec("actual_load", "query_load", _load_to_frame,
                ("zone", "ts_utc")),
    DatasetSpec("actual_generation", "query_generation", _generation_to_frame,
                ("zone", "ts_utc", "production_type", "measure")),
)


# --- Results ----------------------------------------------------------------


@dataclass(frozen=True)
class ZoneResult:
    dataset: str
    zone: str
    status: str  # "ok", "partial", "no_data" or "failed
    rows: int = 0
    intervals: int = 0  # distinct timestamps; for generation this is not rows
    detail: str = ""


@dataclass(frozen=True)
class ExtractResult:
    zones: list[ZoneResult]
    files: dict[str, Path]  # dataset name -> local parquet written

    @property
    def all_ok(self) -> bool:
        return all(z.status == "ok" for z in self.zones)


# --- Main entry point -------------------------------------------------------


def extract_day(
    delivery_date: date,
    client: EntsoePandasClient,
    seed_path: Path,
    out_dir: Path,
) -> ExtractResult:
    """Fetch every dataset for every active zone on one delivery day.

    Writes one parquet file per dataset that returned any data, under
    out_dir/<dataset>/delivery_date=<date>/. Returns each zone's outcome
    and the files written.
    """
    start, end = day_window_utc(delivery_date)
    zones = active_zones(seed_path, delivery_date)
    logger.info("%s: window %s -> %s, %d zones", delivery_date, start, end, len(zones))

    zone_results: list[ZoneResult] = []
    files: dict[str, Path] = {}

    for spec in DATASETS:
        frames = []
        for zone in zones:
            result, frame = _fetch_zone(client, spec, zone, start, end)
            zone_results.append(result)
            if frame is not None:
                frames.append(frame)

        if not frames:
            logger.warning("%s: no zone returned data, nothing written", spec.name)
            continue

        table = pd.concat(frames, ignore_index=True)
        _validate(table, spec, start, end)
        path = _output_path(out_dir, spec.name, delivery_date)
        _write_parquet(table, path)
        files[spec.name] = path
        logger.info("%s: wrote %d rows to %s", spec.name, len(table), path)

    return ExtractResult(zones=zone_results, files=files)


def _fetch_zone(
    client: EntsoePandasClient,
    spec: DatasetSpec,
    zone: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[ZoneResult, pd.DataFrame | None]:
    """Fetch and standardise one zone of one dataset. Never raises for API failures."""
    label = f"{spec.name} {zone}"
    query = getattr(client, spec.method)
    try:
        raw = call_with_retry(lambda: query(zone, start=start, end=end), label)
    except NoMatchingDataError:
        # The zone is declared active for this date, so missing data is
        # an incident to report, not an expected gap.
        logger.warning("%s: no data", label)
        return ZoneResult(spec.name, zone, "no_data"), None
    except EntsoeRequestError as exc:
        logger.error("%s", exc)
        return ZoneResult(spec.name, zone, "failed", detail=str(exc)), None
    
    raw = clip_to_window(raw, start, end).tz_convert("UTC")
    frame = spec.to_frame(raw)
    frame.insert(1, "zone", zone)  # column order: ts_utc, zone, values...

    gap = _coverage_gap(raw.index, start, end)
    if gap:
        logger.warning("%s: %s", label, gap)
        return ZoneResult(spec.name, zone, "partial", rows=len(frame),
                          intervals=len(raw.index), detail=gap), frame

    logger.info("%s: %d rows", label, len(frame))
    return ZoneResult(spec.name, zone, "ok", rows=len(frame),
                      intervals=len(raw.index)), frame
    


def _validate(
    table: pd.DataFrame,
    spec: DatasetSpec,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    """Refuse to write a table that does not cover exactly this day, once."""
    if table["ts_utc"].min() < start or table["ts_utc"].max() >= end:
        raise ValueError(f"{spec.name}: timestamps outside [{start}, {end})")
    if table.duplicated(subset=list(spec.key)).any():
        raise ValueError(f"{spec.name}: duplicate rows on key {spec.key}")


def _coverage_gap(
    index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp
) -> str:
    """Return "" if the series covers the window seamlessly, else what is wrong.
    """
    if len(index) < 2:
        return f"only {len(index)} timestamp(s)"

    steps = index.to_series().diff().dropna().unique()
    step = pd.Timedelta(steps.min())

    if index[0] != start:
        return f"starts at {index[0]}, not at {start}"
    if index[-1] + step != end:
        return f"ends at {index[-1]}, short of {end}"
    if len(steps) > 1:
        return f"largest interval {pd.Timedelta(steps.max())}, shortest {step}"
    return ""


def _output_path(out_dir: Path, dataset: str, delivery_date: date) -> Path:
    iso = delivery_date.isoformat()
    return out_dir / dataset / f"delivery_date={iso}" / f"{dataset}_{iso}.parquet"


def _write_parquet(table: pd.DataFrame, path: Path) -> None:
    """Write atomically: a crash mid-write never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    # BigQuery timestamps have microsecond precision.
    table.to_parquet(tmp, index=False, coerce_timestamps="us")
    tmp.replace(path)