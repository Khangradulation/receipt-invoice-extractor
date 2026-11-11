# Monthly budget whose notifications go to Pub/Sub, where the kill-switch function detaches
# billing at the limit. The function code is deployed by ops/gcp (see its README); this module
# owns the budget, topic, service account and permissions.
variable "project_id" { type = string }
variable "project_number" { type = string }
variable "billing_account" { type = string }
variable "amount" {
  description = "Monthly limit in the billing account currency (whole units)"
  type        = number
}
variable "currency" {
  type    = string
  default = "USD"
}
variable "display_name" { type = string }
variable "topic" {
  type    = string
  default = "budget-alerts"
}

resource "google_pubsub_topic" "alerts" {
  project = var.project_id
  name    = var.topic
}

resource "google_pubsub_topic_iam_member" "budget_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.alerts.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:billing-budget-alert@system.gserviceaccount.com"
}

resource "google_billing_budget" "this" {
  billing_account = var.billing_account
  display_name    = var.display_name

  budget_filter {
    projects               = ["projects/${var.project_number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "EXCLUDE_ALL_CREDITS" # count real usage, even while credits pay
  }
  amount {
    specified_amount {
      currency_code = var.currency
      units         = tostring(var.amount)
    }
  }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }

  all_updates_rule {
    pubsub_topic   = google_pubsub_topic.alerts.id
    schema_version = "1.0"
  }
}

resource "google_service_account" "kill_switch" {
  project      = var.project_id
  account_id   = "budget-kill-switch"
  display_name = "Budget kill switch (detaches billing at budget)"
}

resource "google_project_iam_custom_role" "reader" {
  project     = var.project_id
  role_id     = "killSwitchProjectReader"
  title       = "Kill switch: read project billing info"
  description = "Lets the budget kill switch read whether billing is enabled"
  permissions = ["resourcemanager.projects.get"]
}

resource "google_project_iam_member" "kill_switch" {
  for_each = toset(["roles/billing.projectManager", google_project_iam_custom_role.reader.name])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.kill_switch.email}"
}

output "topic" { value = google_pubsub_topic.alerts.id }
output "kill_switch_email" { value = google_service_account.kill_switch.email }
