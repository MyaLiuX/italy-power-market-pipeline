"""Upload raw extract files to the GCS landing zone.

One object per dataset and delivery day. The object name is derived from the
dataset and the date alone, so re-running a day writes to the same name and
replaces the object instead of adding a second file.
"""

import logging
from datetime import date
from pathlib import Path

from google.cloud import storage
from google.cloud.storage.retry import DEFAULT_RETRY

logger = logging.getLogger(__name__)

UPLOAD_TIMEOUT_SECONDS = 120  # per attempt: a stalled upload must not hang


def blob_name(dataset: str, delivery_date: date) -> str:
    """Return the object name for one dataset and one delivery day.
    """
    iso = delivery_date.isoformat()
    return f"{dataset}/delivery_date={iso}/{dataset}_{iso}.parquet"


def open_bucket(project_id: str, bucket_name: str) -> storage.Bucket:
    """Return a handle to the landing zone bucket.
    """
    client = storage.Client(project=project_id)
    return client.bucket(bucket_name)


def upload_file(bucket: storage.Bucket, local_path: Path, name: str) -> str:
    """Upload one file to `name`, replacing any object already at that name.

    Returns the gs:// URI written.
    """
    blob = bucket.blob(name)
    blob.upload_from_filename(
        local_path,
        timeout=UPLOAD_TIMEOUT_SECONDS,
        retry=DEFAULT_RETRY,
    )
    uri = f"gs://{bucket.name}/{name}"
    logger.info("uploaded %s -> %s (generation %s)", local_path, uri, blob.generation)
    return uri


def upload_day(
    bucket: storage.Bucket,
    files: dict[str, Path],
    delivery_date: date,
) -> list[str]:
    """Upload one delivery day's files to the landing zone.
    """
    return [
        upload_file(bucket, path, blob_name(dataset, delivery_date))
        for dataset, path in files.items()
    ]