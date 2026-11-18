# Input variables. Values are supplied in terraform.tfvars, which is
# gitignored — this file declares only the shape, not the values.

variable "project_id" {
  description = "GCP project ID where all resources are created."
  type        = string
}

variable "region" {
  description = "Region for the GCS bucket and BigQuery datasets. europe-west8 is Milan, closest to the Italian market data this project handles."
  type        = string
  default     = "europe-west8"
}

variable "bucket_name" {
  description = "Name of the GCS bucket for the raw landing zone. Must be globally unique across all of GCP."
  type        = string
}