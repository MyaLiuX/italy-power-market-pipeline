# Pins the Terraform CLI and provider versions this project is built against.
# Without pinning, a future provider release could change resource behaviour
# and break an apply that worked yesterday.

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}