variable "project_id" {
  description = "GCP project ID"
  type        = string
}
variable "project_number" {
  description = "GCP project number (used by the budget filter)"
  type        = string
}
variable "region" {
  type    = string
  default = "us-central1"
}
variable "environment" {
  type    = string
  default = "dev"
}
variable "billing_account" {
  description = "Billing account ID (XXXXXX-XXXXXX-XXXXXX)"
  type        = string
}
variable "budget_amount" {
  description = "Monthly budget (USD) at which the kill switch detaches billing"
  type        = number
  default     = 10
}
variable "github_repository" {
  description = "owner/name allowed to deploy via Workload Identity Federation"
  type        = string
}
variable "github_owner_id" {
  description = "Numeric GitHub ID of the repository owner; pins WIF to that account even if the name is reused"
  type        = string
  default     = null
}
variable "developer_members" {
  description = "Developers who may sign URLs as the API service account when running locally (e.g. user:you@example.com)"
  type        = list(string)
  default     = []
}
variable "web_origins" {
  description = "Extra browser origins (bucket and API CORS); the frontend's run.app URL is always allowed"
  type        = list(string)
  default     = ["http://localhost:5173"]
}
variable "auth_domains" {
  description = "Extra Firebase sign-in domains; the frontend's run.app host is always allowed"
  type        = list(string)
  default     = ["localhost"]
}
variable "initial_image" {
  description = "Placeholder image for newly created Cloud Run services; CI deploys the real images"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
variable "github_environment" {
  description = "GitHub Actions environment whose jobs may deploy (e.g. dev, production)"
  type        = string
}
variable "terraform_runner_roles" {
  description = "Project roles for a CI Terraform account (prod only; empty = no account)"
  type        = list(string)
  default     = []
}
variable "gemini_model" {
  type    = string
  default = "gemini-3.8-flash"
}
variable "gemini_location" {
  type    = string
  default = "global"
}
variable "supported_currencies" {
  type    = list(string)
  default = ["USD", "CAD", "EUR", "GBP", "AUD", "INR", "JPY", "CHF", "MXN", "NZD", "SGD", "PKR"]
}
variable "notification_channels" {
  description = "Cloud Monitoring notification channel IDs for alerts"
  type        = list(string)
  default     = []
}
