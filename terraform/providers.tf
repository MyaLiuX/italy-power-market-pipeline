# Configures the Google provider. No credentials are set here on purpose:
# the provider falls back to Application Default Credentials, which were
# set up with `gcloud auth application-default login`.

provider "google" {
  project = var.project_id
  region  = var.region
}