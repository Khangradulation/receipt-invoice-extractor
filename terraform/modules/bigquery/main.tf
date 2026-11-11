# Analytics dataset and tables. Table definitions come from tables.json, which is generated from
# backend/shared/src/receipt_shared/analytics/schema.py (`make sql-schema`) and drift-tested.
variable "project_id" { type = string }
variable "dataset_id" { type = string }
variable "location" { type = string }
variable "labels" { type = map(string) }
variable "iam_members" {
  description = "List of { role, member } granted on this dataset only"
  type        = list(object({ role = string, member = string }))
  default     = []
}

locals {
  tables = jsondecode(file("${path.module}/tables.json"))
}

resource "google_bigquery_dataset" "this" {
  project     = var.project_id
  dataset_id  = var.dataset_id
  location    = var.location
  description = "Receipt & invoice extractor analytics"
  labels      = var.labels

  lifecycle {
    prevent_destroy = true
    # Access is managed with google_bigquery_dataset_iam_member below (non-authoritative).
    ignore_changes = [access]
  }
}

resource "google_bigquery_table" "this" {
  for_each            = local.tables
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.this.dataset_id
  table_id            = each.key
  description         = each.value.description
  deletion_protection = true
  labels              = var.labels
  clustering          = length(each.value.clustering) > 0 ? each.value.clustering : null

  time_partitioning {
    type  = each.value.partition.type
    field = each.value.partition.field
  }

  # Empty descriptions are omitted, as BigQuery stores them.
  schema = jsonencode([
    for f in each.value.schema : { for k, v in f : k => v if !(k == "description" && v == "") }
  ])

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_bigquery_dataset_iam_member" "this" {
  for_each   = { for b in var.iam_members : "${b.role} ${b.member}" => b }
  project    = var.project_id
  dataset_id = google_bigquery_dataset.this.dataset_id
  role       = each.value.role
  member     = each.value.member
}

output "dataset_id" { value = google_bigquery_dataset.this.dataset_id }
output "tables" { value = keys(google_bigquery_table.this) }
