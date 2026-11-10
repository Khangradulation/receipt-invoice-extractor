#!/usr/bin/env bash
# Build the worker image with Cloud Build, deploy it to Cloud Run, and ensure the Eventarc
# trigger. Billable (Cloud Build minutes, Cloud Run, Artifact Registry storage).
#
#   PROJECT_ID=receipt-extractor-lkmljr ./ops/gcp/deploy-worker.sh
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-${PROJECT_ID}-documents}"
REPO="${REPO:-receipt-extractor}"
SERVICE="${SERVICE:-receipt-worker}"
TAG="${TAG:-$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- backend || echo -dirty)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/worker:${TAG}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
SUPPORTED_CURRENCIES="${SUPPORTED_CURRENCIES:-USD,CAD,EUR,GBP,AUD,INR,JPY,CHF,MXN,NZD,SGD,PKR}"
WORKER_SA="receipt-worker@${PROJECT_ID}.iam.gserviceaccount.com"
EVENTARC_SA="receipt-eventarc@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA="receipt-build@${PROJECT_ID}.iam.gserviceaccount.com"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Building ${IMAGE}"
gcloud builds submit "${ROOT}/backend" --project "$PROJECT_ID" --region "$REGION" \
  --config "${ROOT}/ops/gcp/cloudbuild-image.yaml" \
  --service-account "projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}" \
  --gcs-source-staging-dir "gs://${PROJECT_ID}_cloudbuild/source" \
  --substitutions "_SERVICE=worker,_IMAGE=${IMAGE}"

echo "==> Deploying ${SERVICE}"
gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --image "$IMAGE" \
  --service-account "$WORKER_SA" \
  --no-allow-unauthenticated \
  --ingress internal \
  --cpu 1 --memory 1Gi --concurrency 4 \
  --timeout 300 --min-instances 0 --max-instances 3 \
  --labels app=receipt-extractor,component=worker \
  --set-env-vars "^|^ENVIRONMENT=dev|LOG_LEVEL=INFO|GCP_PROJECT_ID=${PROJECT_ID}|GCS_UPLOAD_BUCKET=${BUCKET}|GEMINI_MODEL=${GEMINI_MODEL}|GEMINI_LOCATION=${GEMINI_LOCATION}|SUPPORTED_CURRENCIES=${SUPPORTED_CURRENCIES}" \
  --quiet

gcloud run services add-iam-policy-binding "$SERVICE" --project "$PROJECT_ID" \
  --region "$REGION" --member "serviceAccount:${EVENTARC_SA}" --role roles/run.invoker >/dev/null

echo "==> Eventarc trigger"
TRIGGER="receipt-upload-finalized"
if ! gcloud eventarc triggers describe "$TRIGGER" --location "$REGION" --project "$PROJECT_ID" \
  >/dev/null 2>&1; then
  gcloud eventarc triggers create "$TRIGGER" --project "$PROJECT_ID" --location "$REGION" \
    --destination-run-service "$SERVICE" --destination-run-region "$REGION" \
    --destination-run-path /events/storage \
    --event-filters "type=google.cloud.storage.object.v1.finalized" \
    --event-filters "bucket=${BUCKET}" \
    --service-account "$EVENTARC_SA"
fi

# Eventarc's Pub/Sub subscription: allow long-running deliveries and back off between retries.
SUB="$(gcloud eventarc triggers describe "$TRIGGER" --location "$REGION" --project "$PROJECT_ID" \
  --format='value(transport.pubsub.subscription)')"
gcloud pubsub subscriptions update "$SUB" --project "$PROJECT_ID" \
  --ack-deadline 600 --min-retry-delay 10s --max-retry-delay 600s >/dev/null

echo "==> Deployed ${IMAGE}"
gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --format 'value(status.url,status.latestReadyRevisionName)'
