#!/usr/bin/env bash
# Phase 6 bootstrap: BigQuery dataset, tables (from sql/schema) and dataset-scoped IAM.
# Idempotent (CREATE ... IF NOT EXISTS). Phase 11 moves this into Terraform.
#
#   PROJECT_ID=my-project ./ops/gcp/bootstrap-bigquery.sh
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
DATASET="${DATASET:-receipt_analytics}"
LOCATION="${LOCATION:-US}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKER_SA="receipt-worker@${PROJECT_ID}.iam.gserviceaccount.com"
API_SA="receipt-api@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud services enable bigquery.googleapis.com --project "$PROJECT_ID"

echo "==> Dataset ${PROJECT_ID}:${DATASET} (${LOCATION})"
if ! bq --project_id "$PROJECT_ID" show --format=none "${PROJECT_ID}:${DATASET}" >/dev/null 2>&1; then
  bq --project_id "$PROJECT_ID" --location "$LOCATION" mk --dataset \
    --description "Receipt & invoice extractor analytics" \
    --label app:receipt-extractor --label env:dev \
    "${PROJECT_ID}:${DATASET}"
fi

echo "==> Tables"
for f in "${ROOT}"/sql/schema/*.sql; do
  sed "s/{{dataset}}/${PROJECT_ID}.${DATASET}/g" "$f" |
    bq --project_id "$PROJECT_ID" --location "$LOCATION" query --use_legacy_sql=false --quiet >/dev/null
  echo "    $(basename "$f" .sql)"
done

echo "==> IAM (dataset-scoped data access; job creation at project level)"
# Dataset access entries (WRITER = bigquery.dataEditor) on this dataset only. The API needs write
# access because approving a reviewed document loads it into BigQuery. (Dataset IAM policy bindings via `bq add-iam-policy-binding` need allowlisting.)
(cd "${ROOT}/backend" && uv run --quiet python - "$PROJECT_ID" "$DATASET" "$WORKER_SA" "$API_SA" <<'PY'
import sys
from google.cloud import bigquery

project, dataset_id, worker, api = sys.argv[1:5]
client = bigquery.Client(project=project)
dataset = client.get_dataset(f"{project}.{dataset_id}")
wanted = [("WRITER", worker), ("WRITER", api)]
# Drop older/other roles for these accounts so each ends up with exactly the wanted role.
managed = {email for _, email in wanted}
entries = [
    e for e in dataset.access_entries
    if e.entity_id not in managed or (e.role, e.entity_id) in set(wanted)
]
existing = {(e.role, e.entity_id) for e in entries}
for role, email in wanted:
    if (role, email) not in existing:
        entries.append(bigquery.AccessEntry(role=role, entity_type="userByEmail", entity_id=email))
dataset.access_entries = entries
client.update_dataset(dataset, ["access_entries"])
print("    access entries:", sorted((e.role, e.entity_id) for e in entries if e.entity_id in (worker, api)))
PY
)
for sa in "$WORKER_SA" "$API_SA"; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None --quiet \
    --member "serviceAccount:${sa}" --role roles/bigquery.jobUser >/dev/null
done
echo "==> Done"
