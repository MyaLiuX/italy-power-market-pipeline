"""Bidding zone registry, read from the maintained seed file.

The seed is the single source of truth for which zones exist and when.
Zones are declared there, never discovered from API responses: a declared
zone that returns no data is a data quality incident, not a retired zone.
"""

from datetime import date
from pathlib import Path

import pandas as pd


def active_zones(seed_path: Path, on: date) -> list[str]:
    """Return the codes of zones that are valid on the given date.

    Validity is half-open: valid_from is inclusive, valid_to is exclusive,
    and an empty valid_to means the zone is still active.
    """
    zones = pd.read_csv(seed_path)

    # Parse explicitly: an all-empty valid_to column is read as float NaN,
    # which cannot be compared with a date. to_datetime turns it into NaT.
    valid_from = pd.to_datetime(zones["valid_from"])
    valid_to = pd.to_datetime(zones["valid_to"])

    day = pd.Timestamp(on)
    is_active = (valid_from <= day) & (valid_to.isna() | (day < valid_to))

    return zones.loc[is_active, "zone_code"].tolist()