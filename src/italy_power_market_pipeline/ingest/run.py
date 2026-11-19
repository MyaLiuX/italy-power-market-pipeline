"""Run the ingestion for one delivery day or a range of days.

This module holds the policy that ties extraction and upload together: a day
is published only when every declared zone returned data. The CLI and the
Airflow DAG both call in here, so that policy exists in exactly one place.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

from entsoe import EntsoePandasClient
from google.cloud import storage

from italy_power_market_pipeline.ingest.extract import extract_day
from italy_power_market_pipeline.ingest.storage import upload_day

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DayOutcome:
    delivery_date: date
    status: str  # "published", "incomplete" or "failed"
    uris: tuple[str, ...] = ()  # a tuple, so the default is immutable
    detail: str = ""  # why the day was not published


def run_day(
    delivery_date: date,
    client: EntsoePandasClient,
    bucket: storage.Bucket,
    seed_path: Path,
    out_dir: Path,
) -> DayOutcome:
    """Extract one day and publish it only if every zone returned data."""
    result = extract_day(delivery_date, client, seed_path, out_dir)

    if not result.all_ok:
        missing = [f"{z.dataset}/{z.zone}" for z in result.zones if z.status != "ok"]
        logger.warning("%s: incomplete, nothing uploaded", delivery_date)
        return DayOutcome(delivery_date, "incomplete", detail=", ".join(missing))

    uris = upload_day(bucket, result.files, delivery_date)
    return DayOutcome(delivery_date, "published", uris=tuple(uris))


def each_day(start: date, end: date) -> Iterator[date]:
    """Yield every date from start to end, both ends included."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def run_range(
    start: date,
    end: date,
    client: EntsoePandasClient,
    bucket: storage.Bucket,
    seed_path: Path,
    out_dir: Path,
) -> list[DayOutcome]:
    """Run a range one day at a time.
    """
    outcomes: list[DayOutcome] = []
    for day in each_day(start, end):
        try:
            outcomes.append(run_day(day, client, bucket, seed_path, out_dir))
        except Exception as exc:
            logger.exception("%s: failed", day)
            outcomes.append(
                DayOutcome(day, "failed", detail=f"{type(exc).__name__}")
            )
    return outcomes