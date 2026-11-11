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
variable "developer_members" {
  description = "Developers who may sign URLs as the API service account when running locally (e.g. user:you@example.com)"
  type        = list(string)
  default     = []
}
variable "web_origins" {
  description = "Browser origins of the web app (bucket CORS and the API's CORS)"
  type        = list(string)
  default     = ["http://localhost:5173"]
}
variable "auth_domains" {
  description = "Domains allowed to use Firebase sign-in"
  type        = list(string)
  default     = ["localhost"]
}
variable "worker_image" {
  description = "Image used if the worker service has to be created; later images come from CI"
  type        = string
}
variable "api_image" {
  description = "API image; the API service is created only once an image exists (Phase 12 CI)"
  type        = string
  default     = null
}
variable "frontend_image" {
  description = "Frontend image; created only once an image exists (Phase 12 CI)"
  type        = string
  default     = null
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
