# The raw landing zone: ENTSO-E responses land here as files before
# anything is loaded into BigQuery.

resource "google_storage_bucket" "raw" {
  name     = var.bucket_name
  location = var.region

  # Enforces IAM only; disables per-object ACLs. Google's recommended
  # default — permissions are managed in one place instead of two.
  uniform_bucket_level_access = true

  # Guards against a bug that overwrites a good file with a bad one:
  # the previous version stays recoverable.
  versioning {
    enabled = true
  }

  lifecycle_rule {
    # Noncurrent versions are only useful for recovery, not analysis.
    # Delete them after 30 days so versioning doesn't grow without bound.
    condition {
      num_newer_versions = 3
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }

  # Allows `terraform destroy` to remove the bucket even if it still
  # holds objects. Acceptable here because everything in it can be
  # re-fetched from ENTSO-E.
  force_destroy = true
}


# Three datasets, one per layer. Separating them means access and
# retention can be set per layer, and it keeps intermediate models
# out of whatever Power BI connects to.

resource "google_bigquery_dataset" "raw" {
  dataset_id  = "raw"
  location    = var.region
  description = "Landing layer: ENTSO-E data loaded as-is, no transformation."
}

resource "google_bigquery_dataset" "staging" {
  dataset_id  = "staging"
  location    = var.region
  description = "Cleaned and typed data: one row per zone and interval."
}

resource "google_bigquery_dataset" "marts" {
  dataset_id  = "marts"
  location    = var.region
  description = "Star schema consumed by Power BI."
}