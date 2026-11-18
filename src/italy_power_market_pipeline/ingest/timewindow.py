"""Compute the UTC query window for one local market day.

ENTSO-E is queried with explicit start/end timestamps, not with a date.
This module turns a local calendar date into that pair of timestamps.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

# The Italian day-ahead market defines its delivery day in local time.
MARKET_TZ = ZoneInfo("Europe/Rome")


def day_window_utc(
    delivery_date: date,
    tz: ZoneInfo = MARKET_TZ,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the half-open UTC window [start, end) for one local market day.

    The end boundary is derived by advancing the calendar date and only then
    attaching the timezone 
    """
    # Step 1: advance the calendar date.
    next_date = delivery_date + timedelta(days=1)

    # Step 2: attach the market timezone to local midnight of each date.
    # Midnight is never ambiguous or missing in Europe/Rome, because its DST
    # transitions happen at 02:00/03:00 local time.
    local_start = datetime.combine(delivery_date, time.min, tzinfo=tz)
    local_end = datetime.combine(next_date, time.min, tzinfo=tz)

    # Step 3: convert to UTC. entsoe-py expects pandas Timestamps.
    return (
        pd.Timestamp(local_start).tz_convert("UTC"),
        pd.Timestamp(local_end).tz_convert("UTC"),
    )

def clip_to_window(
    data: pd.Series | pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series | pd.DataFrame:
    """Keep only the rows whose timestamp falls in the half-open window [start, end).

    Filters by timestamp, never by position, so it is correct whatever the
    source returns at the edges: entsoe-py's prices include a row at `end`,
    load and generation do not.
    """
    in_window = (data.index >= start) & (data.index < end)
    return data.loc[in_window]