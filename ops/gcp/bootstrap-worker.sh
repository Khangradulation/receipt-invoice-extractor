#!/usr/bin/env bash
# Phase 5 bootstrap: worker/Eventarc/build service accounts, Artifact Registry, permissions.
# Idempotent. Run after bootstrap-storage.sh. Phase 11 moves this into Terraform.
#
#   PROJECT_ID=receipt-extractor-lkmljr ./ops/gcp/bootstrap-worker.sh
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-${PROJECT_ID}-documents}"
REPO="${REPO:-receipt-extractor}"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

WORKER_SA="receipt-worker@${PROJECT_ID}.iam.gserviceaccount.com"
EVENTARC_SA="receipt-eventarc@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA="receipt-build@${PROJECT_ID}.iam.gserviceaccount.com"

ensure_sa() {  # name, display name
  local email="$1@${PROJECT_ID}.iam.gserviceaccount.com"
  gcloud iam service-accounts describe "$email" --project "$PROJECT_ID" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$1" --project "$PROJECT_ID" --display-name "$2"
}
project_role() {  # member, role — retried: new service accounts take a moment to propagate
  local i
  for i in 1 2 3 4 5 6; do
    if gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None --quiet \
      --member "$1" --role "$2" >/dev/null 2>&1; then
      return 0
    fi
    sleep 10
  done
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None --quiet \
    --member "$1" --role "$2" >/dev/null
}

echo "==> Enabling APIs"
gcloud services enable run.googleapis.com eventarc.googleapis.com pubsub.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com \
  --project "$PROJECT_ID"

echo "==> Service accounts"
ensure_sa receipt-worker "Receipt extractor worker (Cloud Run)"
ensure_sa receipt-eventarc "Receipt extractor Eventarc trigger (invokes the worker)"
ensure_sa receipt-build "Receipt extractor image builds (Cloud Build)"

echo "==> Worker permissions (least privilege)"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member "serviceAccount:${WORKER_SA}" --role roles/storage.objectViewer >/dev/null
project_role "serviceAccount:${WORKER_SA}" roles/datastore.user
project_role "serviceAccount:${WORKER_SA}" roles/aiplatform.user

echo "==> Eventarc permissions"
project_role "serviceAccount:${EVENTARC_SA}" roles/eventarc.eventReceiver
# Direct Cloud Storage events are published by the Cloud Storage service agent.
GCS_AGENT="$(gcloud storage service-agent --project "$PROJECT_ID" | tr -d '[:space:]')"
project_role "serviceAccount:${GCS_AGENT}" roles/pubsub.publisher
# The Pub/Sub service agent mints the OIDC tokens Eventarc uses to call Cloud Run.
project_role "serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  roles/iam.serviceAccountTokenCreator

echo "==> Artifact Registry ${REPO}"
gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT_ID" \
  >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$REPO" --repository-format docker \
    --location "$REGION" --project "$PROJECT_ID" \
    --description "Receipt extractor container images" \
    --labels app=receipt-extractor
gcloud artifacts repositories add-iam-policy-binding "$REPO" --location "$REGION" \
  --project "$PROJECT_ID" --member "serviceAccount:${BUILD_SA}" \
  --role roles/artifactregistry.writer >/dev/null
# Keep the 10 most recent images per package; delete untagged images after 7 days.
cat > /tmp/receipt-ar-cleanup.json <<'JSON'
[
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 10}},
  {"name": "delete-untagged", "action": {"type": "Delete"},
   "condition": {"tagState": "UNTAGGED", "olderThan": "604800s"}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "$REPO" --location "$REGION" \
  --project "$PROJECT_ID" --policy /tmp/receipt-ar-cleanup.json --no-dry-run >/dev/null

echo "==> Build permissions"
project_role "serviceAccount:${BUILD_SA}" roles/logging.logWriter
# gcloud builds submit stages the source in gs://PROJECT_cloudbuild.
gcloud storage buckets describe "gs://${PROJECT_ID}_cloudbuild" >/dev/null 2>&1 ||
  gcloud storage buckets create "gs://${PROJECT_ID}_cloudbuild" --project "$PROJECT_ID" \
    --location "$REGION" --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding "gs://${PROJECT_ID}_cloudbuild" \
  --member "serviceAccount:${BUILD_SA}" --role roles/storage.objectViewer >/dev/null

echo "==> Done"
