"""Smoke-test the GCS landing zone with a file that already exists locally.

Usage, from the repo root:
    uv run python scripts/check_gcs.py \
        --file data/raw/day_ahead_prices/delivery_date=2026-11-15/day_ahead_prices_2026-11-15.parquet \
        --dataset day_ahead_prices --date 2026-11-15

Uploads the same file twice, which answers three questions at once: do the
credentials work, does the object land on the partitioned path, and does a
re-run replace the object instead of adding one.
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from italy_power_market_pipeline.ingest.storage import (
    blob_name,
    open_bucket,
    upload_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, required=True, help="local parquet")
    parser.add_argument("--dataset", required=True, help="e.g. day_ahead_prices")
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    load_dotenv()
    project_id = os.environ.get("GCP_PROJECT_ID")
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not project_id or not bucket_name:
        sys.exit("GCP_PROJECT_ID and GCS_BUCKET_NAME must be set in .env")
    if not args.file.is_file():
        sys.exit(f"no such file: {args.file} - run extract_one_day.py first")

    bucket = open_bucket(project_id, bucket_name)
    if not bucket.exists():
        # Wrong name, wrong project, or `terraform apply` has not run yet.
        sys.exit(f"bucket {bucket_name} is not reachable")

    name = blob_name(args.dataset, args.date)
    prefix = name.rsplit("/", 1)[0] + "/"

    for attempt in (1, 2):
        upload_file(bucket, args.file, name)
        live = list(bucket.list_blobs(prefix=prefix))
        versions = list(bucket.list_blobs(prefix=prefix, versions=True))
        print(f"\nafter upload {attempt}: {len(live)} live, {len(versions)} version(s)")
        for blob in versions:
            print(f"  {blob.name}  generation={blob.generation}  size={blob.size}")


if __name__ == "__main__":
    main()