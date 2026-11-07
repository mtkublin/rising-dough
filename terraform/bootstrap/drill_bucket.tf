# T-D92 / ADR-0100: separate drill state bucket in the DRILL project, so a
# drill-scoped CI credential never needs access to the prod project's state
# bucket. Same hardening as the prod state bucket (main.tf). The bucket policy
# is attached by the bootstrap/ci stack, which knows the CI application ids.
# Additive: the prod state bucket in main.tf is untouched.
variable "drill_project_id" {
  description = "Scaleway project id of the drill environment (owns the drill state bucket)."
  type        = string
}

variable "drill_bucket_name" {
  description = "Name of the drill Terraform remote-state bucket (must match terraform/envs/drill/backend.hcl)."
  type        = string
  default     = "budget-planner-tfstate-drill-pl-waw"
}

resource "scaleway_object_bucket" "tfstate_drill" {
  name       = var.drill_bucket_name
  region     = var.region
  project_id = var.drill_project_id

  force_destroy = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    id      = "expire-noncurrent-state-90d"
    enabled = true

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload_days = 7
  }

  tags = {
    managed_by = "terraform"
    project    = "budget-planner"
    role       = "terraform-state-drill"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "scaleway_object_bucket_acl" "tfstate_drill" {
  bucket     = scaleway_object_bucket.tfstate_drill.name
  region     = var.region
  project_id = var.drill_project_id
  acl        = "private"
}

output "drill_bucket_name" {
  description = "Drill state bucket name."
  value       = scaleway_object_bucket.tfstate_drill.name
}
