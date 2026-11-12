#!/usr/bin/env bash
# Phase 4 bootstrap: private document bucket, Firestore, and the API service account.
# Idempotent: safe to re-run. Phase 11 moves these resources into Terraform.
#
#   PROJECT_ID=my-project ./ops/gcp/bootstrap-storage.sh
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-${PROJECT_ID}-documents}"
API_SA_NAME="${API_SA_NAME:-receipt-api}"
API_SA="${API_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> Enabling APIs"
gcloud services enable storage.googleapis.com firestore.googleapis.com \
  iamcredentials.googleapis.com --project "$PROJECT_ID"

echo "==> Bucket gs://${BUCKET}"
if ! gcloud storage buckets describe "gs://${BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET}" --project "$PROJECT_ID" \
    --location "$REGION" --default-storage-class STANDARD \
    --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://${BUCKET}" \
  --versioning \
  --public-access-prevention \
  --uniform-bucket-level-access \
  --lifecycle-file "${HERE}/bucket-lifecycle.json" \
  --cors-file "${HERE}/bucket-cors.json" \
  --update-labels app=receipt-extractor,component=documents,env=dev

echo "==> Firestore (default) database"
if ! gcloud firestore databases describe --database="(default)" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud firestore databases create --database="(default)" --location "$REGION" \
    --type firestore-native --project "$PROJECT_ID"
fi

echo "==> API service account ${API_SA}"
if ! gcloud iam service-accounts describe "$API_SA" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$API_SA_NAME" --project "$PROJECT_ID" \
    --display-name "Receipt extractor API (Cloud Run)"
fi

# Bucket-scoped: signed upload URLs act as this account, so it needs create (uploads) and
# read (signed download URLs for the document viewer). No delete, no project-wide storage role.
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member "serviceAccount:${API_SA}" --role roles/storage.objectCreator >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member "serviceAccount:${API_SA}" --role roles/storage.objectViewer >/dev/null
# Firestore has no per-collection IAM; datastore.user is the narrowest data-plane role.
gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None --quiet \
  --member "serviceAccount:${API_SA}" --role roles/datastore.user >/dev/null
# On Cloud Run the API signs URLs through the IAM signBlob API as itself.
gcloud iam service-accounts add-iam-policy-binding "$API_SA" --project "$PROJECT_ID" \
  --member "serviceAccount:${API_SA}" --role roles/iam.serviceAccountTokenCreator >/dev/null

# Local development: let the signed-in developer sign URLs as the API service account.
if [[ -n "${DEVELOPER_EMAIL:-}" ]]; then
  gcloud iam service-accounts add-iam-policy-binding "$API_SA" --project "$PROJECT_ID" \
    --member "user:${DEVELOPER_EMAIL}" --role roles/iam.serviceAccountTokenCreator >/dev/null
fi

echo "==> Done"
echo "GCS_UPLOAD_BUCKET=${BUCKET}"
echo "SIGNING_SERVICE_ACCOUNT=${API_SA}"
