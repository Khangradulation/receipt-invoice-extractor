# Private documents bucket: public access prevention enforced, uniform access, versioning,
# lifecycle rules, CORS for the web app, bucket-scoped IAM.
variable "project_id" { type = string }
variable "name" { type = string }
variable "location" { type = string }
variable "labels" { type = map(string) }
variable "cors_origins" {
  description = "Browser origins allowed to PUT/GET via signed URLs"
  type        = list(string)
}
variable "noncurrent_version_retention_days" {
  type    = number
  default = 30
}
variable "iam_members" {
  description = "List of { role, member } granted on this bucket only"
  type        = list(object({ role = string, member = string }))
  default     = []
}
variable "force_destroy" {
  type    = bool
  default = false
}

resource "google_storage_bucket" "this" {
  project                     = var.project_id
  name                        = var.name
  location                    = upper(var.location)
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy
  labels                      = var.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action { type = "Delete" }
    condition {
      with_state                 = "ARCHIVED"
      days_since_noncurrent_time = var.noncurrent_version_retention_days
    }
  }
  lifecycle_rule {
    action { type = "AbortIncompleteMultipartUpload" }
    condition { age = 1 }
  }
  lifecycle_rule {
    action { type = "Delete" }
    condition {
      age            = 1
      matches_prefix = ["tmp/"]
    }
  }

  cors {
    origin          = var.cors_origins
    method          = ["PUT", "GET", "HEAD"]
    response_header = ["Content-Type", "x-goog-content-length-range", "x-goog-meta-sha256", "ETag"]
    max_age_seconds = 3600
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "this" {
  for_each = { for b in var.iam_members : "${b.role} ${b.member}" => b }
  bucket   = google_storage_bucket.this.name
  role     = each.value.role
  member   = each.value.member
}

output "name" { value = google_storage_bucket.this.name }
output "url" { value = google_storage_bucket.this.url }
