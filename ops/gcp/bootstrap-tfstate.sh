#!/usr/bin/env bash
# Create the Terraform remote-state bucket (Terraform needs it before its first `init`).
# Private, versioned (state history can be restored), uniform access, public access blocked.
# The GCS backend locks state with a lock object, so concurrent runs cannot corrupt it.
#
#   PROJECT_ID=receipt-extractor-lkmljr ./ops/gcp/bootstrap-tfstate.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-${PROJECT_ID}-tfstate}"

if ! gcloud storage buckets describe "gs://${BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET}" --project "$PROJECT_ID" --location "$REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://${BUCKET}" --versioning \
  --update-labels app=receipt-extractor,component=terraform-state >/dev/null
echo "state bucket: gs://${BUCKET}"
