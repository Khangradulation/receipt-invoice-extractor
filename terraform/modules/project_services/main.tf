# Enables Google Cloud APIs. Never disables them on destroy (other workloads may depend on them).
variable "project_id" { type = string }
variable "services" { type = set(string) }

resource "google_project_service" "this" {
  for_each                   = var.services
  project                    = var.project_id
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}

output "services" { value = [for s in google_project_service.this : s.service] }
