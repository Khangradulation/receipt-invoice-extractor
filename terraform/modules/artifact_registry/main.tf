# Docker repository with cleanup policies (keep recent images, delete stale untagged ones).
variable "project_id" { type = string }
variable "location" { type = string }
variable "repository_id" { type = string }
variable "labels" { type = map(string) }
variable "keep_recent" {
  type    = number
  default = 10
}
variable "writer_members" {
  type    = list(string)
  default = []
}
variable "reader_members" {
  type    = list(string)
  default = []
}

resource "google_artifact_registry_repository" "this" {
  project       = var.project_id
  location      = var.location
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = "Receipt extractor container images"
  labels        = var.labels

  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.keep_recent
    }
  }
  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"
    }
  }
}

resource "google_artifact_registry_repository_iam_member" "writers" {
  for_each   = toset(var.writer_members)
  project    = var.project_id
  location   = var.location
  repository = google_artifact_registry_repository.this.repository_id
  role       = "roles/artifactregistry.writer"
  member     = each.value
}

resource "google_artifact_registry_repository_iam_member" "readers" {
  for_each   = toset(var.reader_members)
  project    = var.project_id
  location   = var.location
  repository = google_artifact_registry_repository.this.repository_id
  role       = "roles/artifactregistry.reader"
  member     = each.value
}

output "url" {
  value = "${var.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.this.repository_id}"
}
