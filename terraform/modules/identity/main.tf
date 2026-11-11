# Firebase Authentication (Identity Platform): email/password sign-in and the web origins
# allowed to sign in.
variable "project_id" { type = string }
variable "authorized_domains" { type = list(string) }

resource "google_identity_platform_config" "this" {
  project            = var.project_id
  authorized_domains = var.authorized_domains

  sign_in {
    allow_duplicate_emails = false
    email {
      enabled           = true
      password_required = true
    }
    phone_number {
      enabled = false
    }
  }

  lifecycle {
    # Firebase manages these itself.
    ignore_changes = [client, mfa, monitoring, multi_tenant, quota, blocking_functions]
  }
}
