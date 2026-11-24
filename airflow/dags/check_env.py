"""Check that a task inside the container can reach the project's code, its
configuration and the landing-zone bucket.

Issue 07, step 1. Delete once the real ingestion DAG works: this proves the
container's wiring, not any pipeline behaviour.
"""

import os
from datetime import date
from pathlib import Path

import pendulum

from airflow.sdk import dag, task

# A path inside the container, mounted by docker-compose.override.yml.
SEED_PATH = Path("/usr/local/airflow/seeds/dim_zones.csv")


@dag(
    schedule=None,
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,
    tags=["check"],
)
def check_environment():
    """One task, three checks: the import, the configuration, the bucket."""

    @task
    def report() -> None:
        # Imported inside the task, not at module level. Two reasons: a wrong
        # mount then shows up as a failed task with a readable traceback rather
        # than as a DAG that will not parse, and only the service that executes
        # tasks needs the mount - the one parsing this file does not.
        from italy_power_market_pipeline.ingest.storage import open_bucket
        from italy_power_market_pipeline.ingest.zones import active_zones

        project_id = os.environ["GCP_PROJECT_ID"]
        bucket_name = os.environ["GCS_BUCKET_NAME"]

        print(f"api key present:  {bool(os.environ.get('ENTSOE_API_KEY'))}")
        print(f"project:          {project_id}")
        print(f"bucket:           {bucket_name}")
        print(f"zones:            {active_zones(SEED_PATH, date.today())}")
        print(f"bucket reachable: {open_bucket(project_id, bucket_name).exists()}")

    report()


check_environment()