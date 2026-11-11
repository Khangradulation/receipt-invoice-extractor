# Keyless GitHub Actions -> Google Cloud authentication (Workload Identity Federation).
# Only jobs from the given repository that run in the given GitHub environment (which has its
# own branch/tag and reviewer rules) can impersonate the CI service accounts.
variable "project_id" { type = string }
variable "github_repository" {
  description = "owner/name"
  type        = string
}
variable "pool_id" {
  type    = string
  default = "github"
}
variable "deployer_account_id" {
  type    = string
  default = "receipt-ci-deployer"
}
variable "github_environment" {
  description = "GitHub Actions environment (e.g. dev, production) allowed to impersonate the accounts"
  type        = string
}
variable "deployer_roles" {
  description = "Project roles for the CI deployer"
  type        = list(string)
}
variable "act_as_service_accounts" {
  description = "Runtime service account emails the deployer may deploy services as"
  type        = list(string)
}
variable "terraform_runner_roles" {
  description = "Project roles for a CI account that runs terraform apply (empty = not created)"
  type        = list(string)
  default     = []
}

locals {
  principal = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.this.name}/attribute.environment/${var.github_environment}"
}

resource "google_iam_workload_identity_pool" "this" {
  project                   = var.project_id
  workload_identity_pool_id = var.pool_id
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.this.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.repository"  = "assertion.repository"
    "attribute.ref"         = "assertion.ref"
    "attribute.workflow"    = "assertion.workflow"
    "attribute.environment" = "assertion.environment"
  }
  # Reject tokens from any other repository before they reach IAM.
  attribute_condition = "assertion.repository == \"${var.github_repository}\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = var.deployer_account_id
  display_name = "Receipt extractor CI deployer (GitHub Actions)"
}

resource "google_service_account_iam_member" "wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.principal
}

resource "google_project_iam_member" "deployer" {
  for_each = toset(var.deployer_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "act_as" {
  for_each           = toset(var.act_as_service_accounts)
  service_account_id = "projects/${var.project_id}/serviceAccounts/${each.value}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# Optional: an account for terraform apply from CI (production's protected workflow).
resource "google_service_account" "terraform" {
  count        = length(var.terraform_runner_roles) > 0 ? 1 : 0
  project      = var.project_id
  account_id   = "receipt-ci-terraform"
  display_name = "Receipt extractor CI Terraform runner (GitHub Actions)"
}

resource "google_service_account_iam_member" "terraform_wif" {
  count              = length(google_service_account.terraform)
  service_account_id = google_service_account.terraform[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.principal
}

resource "google_project_iam_member" "terraform" {
  for_each = length(google_service_account.terraform) > 0 ? toset(var.terraform_runner_roles) : toset([])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.terraform[0].email}"
}

output "provider_name" { value = google_iam_workload_identity_pool_provider.github.name }
output "deployer_email" { value = google_service_account.deployer.email }
output "terraform_runner_email" { value = try(google_service_account.terraform[0].email, null) }
