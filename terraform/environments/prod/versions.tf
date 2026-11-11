terraform {
  required_version = ">= 1.7.0, < 2.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.11"
    }
  }
  # Remote state in GCS (created by ops/gcp/bootstrap-tfstate.sh). The GCS backend locks state
  # with a lock object, so concurrent runs cannot corrupt it. Bucket name is passed at init:
  #   terraform init -backend-config="bucket=<project>-tfstate"
  backend "gcs" {
    prefix = "receipt-extractor/prod"
  }
}

provider "google" {
  project               = var.project_id
  region                = var.region
  billing_project       = var.project_id
  user_project_override = true
}
