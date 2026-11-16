# Allow-only bucket policy (ADR-0091). With Version 2023-04-17 anything not
# explicitly allowed is denied, so Deny statements are useless and omitted.
# Provider-free on purpose: tests render it with plain `terraform apply`.
locals {
  resources = [var.bucket_name, "${var.bucket_name}/*"]

  env_statement = {
    Sid       = "AllowEnvApplication"
    Effect    = "Allow"
    Principal = { SCW = ["application_id:${var.env_application_id}"] }
    Action = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListBucketMultipartUploads",
      "s3:ListMultipartUploadParts",
    ]
    Resource = local.resources
  }

  admin_statements = length(var.admin_principals) == 0 ? [] : [{
    Sid       = "AllowOperators"
    Effect    = "Allow"
    Principal = { SCW = var.admin_principals }
    Action    = ["s3:*"]
    Resource  = local.resources
  }]

  readonly_statements = length(var.readonly_principals) == 0 ? [] : [{
    Sid       = "AllowReadOnly"
    Effect    = "Allow"
    Principal = { SCW = var.readonly_principals }
    Action = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucketVersions",
    ]
    Resource = local.resources
  }]

  # ADR-0105: what a refresh of the bucket, its ACL and its policy reads. No objects.
  plan_statements = length(var.plan_principals) == 0 ? [] : [{
    Sid       = "AllowTerraformPlanRead"
    Effect    = "Allow"
    Principal = { SCW = var.plan_principals }
    Action = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetBucketCORS",
      "s3:GetBucketVersioning",
      "s3:GetLifecycleConfiguration",
      "s3:GetBucketTagging",
      "s3:GetBucketAcl",
      "s3:GetBucketPolicy",
      "s3:GetBucketObjectLockConfiguration",
    ]
    Resource = local.resources
  }]
  policy = {
    Version   = "2023-04-17"
    Statement = concat([local.env_statement], local.admin_statements, local.readonly_statements, local.plan_statements)
  }
}
