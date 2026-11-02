# Durability bucket for Litestream snapshots + WAL (ADR-0034).
# ADR-0035 §3: pl-waw, versioning on, SSE on, no public access.
resource "scaleway_object_bucket" "durability" {
  name   = var.bucket_name
  region = var.scaleway_region

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

# Belt-and-braces guard: refuse plaintext (non-TLS) requests at the bucket
# policy layer. ACL=private on the bucket already blocks public access.
resource "scaleway_object_bucket_policy" "durability" {
  bucket = scaleway_object_bucket.durability.name
  region = var.scaleway_region

  policy = jsonencode({
    Version = "2023-04-17"
    Statement = [
      {
        Sid       = "DenyUnencryptedTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          scaleway_object_bucket.durability.name,
          "${scaleway_object_bucket.durability.name}/*",
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      }
    ]
  })
}
