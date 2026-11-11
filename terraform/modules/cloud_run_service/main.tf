# A Cloud Run (v2) service. Terraform owns its configuration; CI owns which image is deployed
# (image changes are ignored after creation), so the two never fight.
variable "project_id" { type = string }
variable "location" { type = string }
variable "name" { type = string }
variable "image" {
  description = "Image used when the service is first created; later deploys come from CI"
  type        = string
}
variable "service_account" { type = string }
variable "env" {
  type    = map(string)
  default = {}
}
variable "ingress" {
  description = "INGRESS_TRAFFIC_ALL | INGRESS_TRAFFIC_INTERNAL_ONLY | INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  type        = string
}
variable "invoker_members" {
  description = "Principals allowed to invoke (use [\"allUsers\"] for a public service)"
  type        = list(string)
  default     = []
}
variable "cpu" {
  type    = string
  default = "1"
}
variable "memory" {
  type    = string
  default = "512Mi"
}
variable "concurrency" {
  type    = number
  default = 80
}
variable "timeout_seconds" {
  type    = number
  default = 60
}
variable "min_instances" {
  type    = number
  default = 0
}
variable "max_instances" {
  type    = number
  default = 3
}
variable "container_port" {
  type    = number
  default = 8080
}
variable "labels" {
  type    = map(string)
  default = {}
}

variable "deletion_protection" {
  description = "Block deletion of the service (including by terraform destroy)"
  type        = bool
  default     = true
}

resource "google_cloud_run_v2_service" "this" {
  project             = var.project_id
  location            = var.location
  name                = var.name
  ingress             = var.ingress
  labels              = var.labels
  deletion_protection = var.deletion_protection

  template {
    service_account                  = var.service_account
    max_instance_request_concurrency = var.concurrency
    timeout                          = "${var.timeout_seconds}s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image
      ports {
        container_port = var.container_port
      }
      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = true
        startup_cpu_boost = true # faster cold starts
      }
      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image, # deployed by CI
      template[0].revision,
      template[0].labels,
      client,
      client_version,
      scaling,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)
  project  = var.project_id
  location = var.location
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = each.value
}

output "name" { value = google_cloud_run_v2_service.this.name }
output "uri" { value = google_cloud_run_v2_service.this.uri }
