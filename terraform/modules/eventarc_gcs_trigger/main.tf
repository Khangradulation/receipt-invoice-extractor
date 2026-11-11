# Direct Cloud Storage "object finalized" events -> a Cloud Run service path.
variable "project_id" { type = string }
variable "location" { type = string }
variable "name" { type = string }
variable "bucket" { type = string }
variable "service" { type = string }
variable "path" { type = string }
variable "service_account" { type = string }

resource "google_eventarc_trigger" "this" {
  project         = var.project_id
  location        = var.location
  name            = var.name
  service_account = var.service_account

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  matching_criteria {
    attribute = "bucket"
    value     = var.bucket
  }

  destination {
    cloud_run_service {
      service = var.service
      region  = var.location
      path    = var.path
    }
  }

  lifecycle {
    ignore_changes = [labels]
  }
}

output "name" { value = google_eventarc_trigger.this.name }
output "subscription" { value = google_eventarc_trigger.this.transport[0].pubsub[0].subscription }
