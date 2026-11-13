# Durability bucket for Litestream snapshots + WAL (ADR-0034).
# ADR-0035 §3: pl-waw, versioning on, SSE on, no public access.
resource "scaleway_object_bucket" "durability" {
  name   = var.bucket_name
  region = var.scaleway_region

  # true for drill only (ADR-0091): terraform destroy must empty the bucket.
  force_destroy = var.force_destroy

  versioning {
    enabled = true
  }

  lifecycle_rule {
    id      = "expire-noncurrent-${var.lifecycle_days}d"
    enabled = true

    noncurrent_version_expiration {
      noncurrent_days = var.lifecycle_days
    }

    abort_incomplete_multipart_upload_days = 7
  }

  # T-D86: drill-only boot diagnostics expire after 7 d (versioned bucket: also
  # drop noncurrent versions and the delete markers).
  dynamic "lifecycle_rule" {
    for_each = var.expire_boot_logs ? [1] : []
    content {
      id      = "expire-boot-logs-7d"
      enabled = true
      prefix  = "boot-logs/"

      expiration {
        days = 7
      }

      noncurrent_version_expiration {
        noncurrent_days = 1
      }

      abort_incomplete_multipart_upload_days = 1
    }
  }

  tags = {
    managed_by = "terraform"
    project    = "budget-planner"
    role       = "litestream-durability"
  }
}

# Private ACL explicit on its own resource (deprecated as a bucket attribute).
resource "scaleway_object_bucket_acl" "durability" {
  bucket = scaleway_object_bucket.durability.name
  region = var.scaleway_region
  acl    = "private"
}

# Allow-list policy (ADR-0091): per-env isolation + operator/read-only access.
# Do not add Deny statements; they are ignored with Version 2023-04-17.
module "policy" {
  source = "../bucket_policy"

  bucket_name         = scaleway_object_bucket.durability.name
  env_application_id  = var.env_application_id
  admin_principals    = var.admin_principals
  readonly_principals = var.readonly_principals
}

resource "scaleway_object_bucket_policy" "durability" {
  bucket = scaleway_object_bucket.durability.name
  region = var.scaleway_region
  policy = module.policy.policy_json
}
