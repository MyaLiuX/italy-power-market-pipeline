"""Eyeball the query window on four dates, including both DST transitions."""

from datetime import date
import pandas as pd

from italy_power_market_pipeline.ingest.timewindow import clip_to_window, day_window_utc

# A fake series shaped like entsoe-py's prices: 15-minute steps in Rome time,
# including one row at the window's end that belongs to the next day.
start, end = day_window_utc(date(2026, 11, 15))
index = pd.date_range(start, end, freq="15min").tz_convert("Europe/Rome")
fake_prices = pd.Series(range(len(index)), index=index)

clipped = clip_to_window(fake_prices, start, end)
print(f"\nclip: {len(fake_prices)} -> {len(clipped)} rows | last: {clipped.index[-1]}")