"""
Learning DAG for Issue 03: TaskFlow API basics.
Not part of the production pipeline - safe to delete later.
"""

import pendulum

from airflow.sdk import dag, task


@dag(
    # No automatic schedule: this DAG only runs when triggered manually.
    schedule=None,
    # Fixed point in the past. Never use datetime.now() here - see notes.
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    # Do not create runs for every interval between start_date and today.
    catchup=False,
    tags=["learning"],
    default_args={
        "retries": 2,
        "retry_delay": pendulum.duration(seconds=30),
    },
)
def example_taskflow():
    """Two tasks: one produces a payload, the other consumes it."""

    @task
    def extract() -> dict:
        """Stand-in for the ENTSO-E call. Returns a JSON-serialisable dict."""
        prices = [95.4, 102.1, 160.7, -3.2]
        return {"zone": "IT_NORD", "prices": prices}

    @task
    def summarise(payload: dict) -> None:
        """Consumes the upstream return value and logs a summary."""
        prices = payload["prices"]
        print(f"zone={payload['zone']} n={len(prices)} mean={sum(prices) / len(prices):.2f}")

    @task
    def flaky(payload: dict) -> str:
        """Fails on every attempt until a marker file exists in the container."""
        from pathlib import Path

        marker = Path("/tmp/flaky_ok")
        if not marker.exists():
            raise RuntimeError("downstream service unavailable")
        return f"ok with {len(payload['prices'])} prices"

    # Calling extract() does NOT run it - it returns a reference to its output.
    data = extract()
    summarise(data)
    flaky(data)

# The DAG only exists once the decorated function is called at module level.
example_taskflow()