# Non-authoritative project-level role grants (adds members; never removes anyone else's access).
variable "project_id" { type = string }
variable "bindings" {
  description = "List of { role, member }"
  type        = list(object({ role = string, member = string }))
}

resource "google_project_iam_member" "this" {
  for_each = { for b in var.bindings : "${b.role} ${b.member}" => b }
  project  = var.project_id
  role     = each.value.role
  member   = each.value.member
}
