# One service account per workload (API, worker, Eventarc invoker, builds, CI deployer, ...).
variable "project_id" { type = string }
variable "accounts" {
  description = "account_id => display name"
  type        = map(string)
}

resource "google_service_account" "this" {
  for_each     = var.accounts
  project      = var.project_id
  account_id   = each.key
  display_name = each.value
}

output "emails" { value = { for k, sa in google_service_account.this : k => sa.email } }
output "members" { value = { for k, sa in google_service_account.this : k => "serviceAccount:${sa.email}" } }
output "names" { value = { for k, sa in google_service_account.this : k => sa.name } }
