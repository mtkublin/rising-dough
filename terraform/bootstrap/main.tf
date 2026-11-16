# Terraform remote-state bucket (ADR-0096, amends ADR-0035 section 4).
# Applied once by the operator with local state; the main stack stores its own
# state in this bucket. No bucket policy on purpose: a wrong policy locks the
# owner out (ADR-0091); Scaleway buckets are private by default.
resource "scaleway_object_bucket" "tfstate" {
  name   = var.bucket_name
  region = var.region

  force_destroy = false

  versioning {
    enabled = true
  }

  # Keep history for rollback, but do not grow without bound.
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
    role       = "terraform-state"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "scaleway_object_bucket_acl" "tfstate" {
  bucket = scaleway_object_bucket.tfstate.name
  region = var.region
  acl    = "private"
}
