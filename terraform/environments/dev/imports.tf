# Resources created before Terraform (by the ops/gcp/*.sh scripts) are adopted, not recreated.
# Import blocks are no-ops once a resource is in state, so they can stay.
# IAM members aren't imported: granting an existing binding is a no-op.

locals {
  p = var.project_id
}

import {
  to = module.stack.module.documents.google_storage_bucket.this
  id = "${local.p}-documents"
}
import {
  to = module.stack.google_storage_bucket.cloudbuild
  id = "${local.p}_cloudbuild"
}
import {
  for_each = toset(["receipt-api", "receipt-worker", "receipt-eventarc", "receipt-build"])
  to       = module.stack.module.service_accounts.google_service_account.this[each.key]
  id       = "projects/${local.p}/serviceAccounts/${each.key}@${local.p}.iam.gserviceaccount.com"
}
import {
  to = module.stack.module.firestore.google_firestore_database.this
  id = "projects/${local.p}/databases/(default)"
}
import {
  to = module.stack.module.firestore.google_firestore_index.by_user
  id = "projects/${local.p}/databases/(default)/collectionGroups/documents/indexes/CICAgOjXh4EK"
}
import {
  to = module.stack.module.firestore.google_firestore_index.by_user_status
  id = "projects/${local.p}/databases/(default)/collectionGroups/documents/indexes/CICAgJiUpoMK"
}
import {
  to = module.stack.module.bigquery.google_bigquery_dataset.this
  id = "projects/${local.p}/datasets/receipt_analytics"
}
import {
  for_each = toset(["documents", "extracted_transactions", "line_items", "review_records", "extraction_metrics"])
  to       = module.stack.module.bigquery.google_bigquery_table.this[each.key]
  id       = "projects/${local.p}/datasets/receipt_analytics/tables/${each.key}"
}
import {
  to = module.stack.module.registry.google_artifact_registry_repository.this
  id = "projects/${local.p}/locations/${var.region}/repositories/receipt-extractor"
}
import {
  to = module.stack.module.worker.google_cloud_run_v2_service.this
  id = "projects/${local.p}/locations/${var.region}/services/receipt-worker"
}
import {
  to = module.stack.module.upload_trigger.google_eventarc_trigger.this
  id = "projects/${local.p}/locations/${var.region}/triggers/receipt-upload-finalized"
}
import {
  to = module.stack.module.budget_guard.google_pubsub_topic.alerts
  id = "projects/${local.p}/topics/budget-alerts"
}
import {
  to = module.stack.module.budget_guard.google_billing_budget.this
  id = "billingAccounts/${var.billing_account}/budgets/acef4d14-a41b-4f99-a4cd-e1037a337d37"
}
import {
  to = module.stack.module.budget_guard.google_service_account.kill_switch
  id = "projects/${local.p}/serviceAccounts/budget-kill-switch@${local.p}.iam.gserviceaccount.com"
}
import {
  to = module.stack.module.budget_guard.google_project_iam_custom_role.reader
  id = "projects/${local.p}/roles/killSwitchProjectReader"
}
import {
  to = module.stack.module.identity.google_identity_platform_config.this
  id = "projects/${local.p}/config"
}
