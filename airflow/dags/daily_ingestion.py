"""Ingest one delivery day of ENTSO-E data and publish it to the landing zone.

Issue 07. The day a run processes is the day that run stands for, taken from
its own data interval rather than from the clock, so that re-running a past run
fetches the day it was created for.
"""

import os
from pathlib import Path

import pendulum

from airflow.sdk import dag, get_current_context, task

# Paths inside the container, mounted by docker-compose.override.yml.
SEED_PATH = Path("/usr/local/airflow/seeds/dim_zones.csv")
OUT_DIR = Path("/usr/local/airflow/data/raw")


@dag(
    # Evaluated in the DAG's own timezone, so it stays at 08:00 Rome through
    # both DST changes. That is eight hours past the end of the delivery day;
    # the longest publication lag measured so far was under six.
    schedule="0 8 * * *",
    start_date=pendulum.datetime(2026, 11, 1, tz="Europe/Rome"),
    # No automatic backfill. Loading history needs one request per month rather
    # than one per day, which is a separate DAG (issue 08).
    catchup=False,
    tags=["ingestion"],
    default_args={
        # Plain retries, because the usual reason a day is incomplete is that
        # the source has not finished publishing it yet.
        "retries": 3,
        "retry_delay": pendulum.duration(hours=1),
    },
)
def daily_ingestion():
    """One task: extract a day, publish it only if every zone is complete."""

    @task
    def ingest() -> str:
        # Imported inside the task, not at module level: only the process that
        # executes tasks has the package mounted, and a wrong mount then fails
        # this task instead of breaking DAG parsing.
        from italy_power_market_pipeline.ingest.client import make_client
        from italy_power_market_pipeline.ingest.run import run_day
        from italy_power_market_pipeline.ingest.storage import open_bucket

        context = get_current_context()
        delivery_date = context["data_interval_start"].date()
        print(f"delivery date: {delivery_date}")

        client = make_client(os.environ["ENTSOE_API_KEY"])
        bucket = open_bucket(
            os.environ["GCP_PROJECT_ID"], os.environ["GCS_BUCKET_NAME"]
        )

        outcome = run_day(delivery_date, client, bucket, SEED_PATH, OUT_DIR)
        print(f"{outcome.delivery_date}  {outcome.status}  {outcome.detail}")

        if outcome.status != "published":
            # A plain exception, so that the task retries.
            raise RuntimeError(f"{outcome.delivery_date}: {outcome.status}")

        return str(outcome.delivery_date)

    ingest()


daily_ingestion()