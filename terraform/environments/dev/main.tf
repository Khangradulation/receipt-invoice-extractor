# DEV environment: all resources are defined once in modules/stack; this file only
# passes this environment's settings (terraform.tfvars).
module "stack" {
  source = "../../modules/stack"

  project_id             = var.project_id
  project_number         = var.project_number
  region                 = var.region
  environment            = var.environment
  billing_account        = var.billing_account
  budget_amount          = var.budget_amount
  github_repository      = var.github_repository
  developer_members      = var.developer_members
  web_origins            = var.web_origins
  auth_domains           = var.auth_domains
  initial_image          = var.initial_image
  github_environment     = var.github_environment
  terraform_runner_roles = var.terraform_runner_roles
  gemini_model           = var.gemini_model
  gemini_location        = var.gemini_location
  supported_currencies   = var.supported_currencies
  notification_channels  = var.notification_channels
}
