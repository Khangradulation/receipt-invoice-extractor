#!/usr/bin/env bash
# Composite indexes for document listing (Phase 7): newest-first per user, optionally by status.
# Idempotent: existing indexes are skipped. Index builds take a few minutes.
#
#   PROJECT_ID=my-project ./ops/gcp/bootstrap-firestore-indexes.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
COLLECTION="${COLLECTION:-documents}"

create() {
  local out
  if ! out="$(gcloud firestore indexes composite create --project "$PROJECT_ID" \
    --collection-group "$COLLECTION" --query-scope COLLECTION --async "$@" 2>&1)"; then
    if grep -qi "already exists" <<<"$out"; then echo "    exists"; else echo "$out" >&2; return 1; fi
  else
    echo "    creating"
  fi
}

echo "==> (user_id, created_at desc, document_id desc)"
create --field-config field-path=user_id,order=ascending \
  --field-config field-path=created_at,order=descending \
  --field-config field-path=document_id,order=descending
echo "==> (user_id, status, created_at desc, document_id desc)"
create --field-config field-path=user_id,order=ascending \
  --field-config field-path=status,order=ascending \
  --field-config field-path=created_at,order=descending \
  --field-config field-path=document_id,order=descending
