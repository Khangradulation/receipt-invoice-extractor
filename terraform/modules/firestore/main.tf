# Firestore (Native mode) operational database + the composite indexes the API needs.
variable "project_id" { type = string }
variable "location" { type = string }
variable "collection" {
  type    = string
  default = "documents"
}

resource "google_firestore_database" "this" {
  project                 = var.project_id
  name                    = "(default)"
  location_id             = var.location
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"

  lifecycle {
    prevent_destroy = true
  }
}

# Newest-first listing per user (GET /documents), optionally filtered by status.
resource "google_firestore_index" "by_user" {
  project    = var.project_id
  database   = google_firestore_database.this.name
  collection = var.collection

  fields {
    field_path = "user_id"
    order      = "ASCENDING"
  }
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
  fields {
    field_path = "document_id"
    order      = "DESCENDING"
  }
  fields {
    field_path = "__name__"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "by_user_status" {
  project    = var.project_id
  database   = google_firestore_database.this.name
  collection = var.collection

  fields {
    field_path = "user_id"
    order      = "ASCENDING"
  }
  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
  fields {
    field_path = "document_id"
    order      = "DESCENDING"
  }
  fields {
    field_path = "__name__"
    order      = "DESCENDING"
  }
}

output "database" { value = google_firestore_database.this.name }
