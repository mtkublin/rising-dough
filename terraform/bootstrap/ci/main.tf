# T-D92 / ADR-0100: least-privilege CI identities, one application per
# environment plus a read-only application for PR plans. Replaces the single
# org-admin key that CI and the laptop used to share.
#
# Local state, NOT committed (it holds the API secret keys; terraform/.gitignore
# ignores *.tfstate and only un-ignores ../terraform.tfstate).

locals {
  key_expires_at = timeadd(plantimestamp(), "${var.ci_key_ttl_hours}h")

  # Actions the Terraform S3 backend needs (state + use_lockfile).
  state_rw_actions = [
    "s3:ListBucket",
    "s3:GetBucketLocation",
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:AbortMultipartUpload",
    "s3:ListBucketMultipartUploads",
    "s3:ListMultipartUploadParts",
  ]
  state_ro_actions = [
    "s3:ListBucket",
    "s3:GetBucketLocation",
    "s3:GetObject",
  ]
}

# ---------------------------------------------------------------- ci-prod
resource "scaleway_iam_application" "ci_prod" {
  name        = "budget-planner-ci-prod"
  description = "CI identity for prod Terraform apply (GitHub environment prod). ADR-0100."
}

resource "scaleway_iam_policy" "ci_prod" {
  name           = "budget-planner-ci-prod"
  description    = "Prod project resources + DNS zone + IAM management for the prod stack (ADR-0100)."
  application_id = scaleway_iam_application.ci_prod.id

  # Prod project: compute, object storage, DNS (the zone lives here).
  rule {
    project_ids          = [var.prod_project_id]
    permission_set_names = ["InstancesFullAccess", "ObjectStorageFullAccess", "DomainsDNSFullAccess"]
  }

  # The env stack creates IAM applications, API keys and policies. Scaleway
  # only offers this at organization scope. Residual risk: see ADR-0100.
  rule {
    organization_id      = var.scaleway_organization_id
    permission_set_names = ["IAMManager"]
  }
}

resource "scaleway_iam_api_key" "ci_prod" {
  application_id     = scaleway_iam_application.ci_prod.id
  description        = "GitHub environment prod: terraform apply (ADR-0100)"
  default_project_id = var.prod_project_id
  expires_at         = local.key_expires_at

  # plantimestamp() moves on every plan; the date is fixed at creation.
  lifecycle {
    ignore_changes = [expires_at]
  }
}

# --------------------------------------------------------------- ci-drill
resource "scaleway_iam_application" "ci_drill" {
  name        = "budget-planner-ci-drill"
  description = "CI identity for drill Terraform (GitHub environment drill). ADR-0100."
}

resource "scaleway_iam_policy" "ci_drill" {
  name           = "budget-planner-ci-drill"
  description    = "Drill project resources + DNS records in the prod-project zone + IAM management (ADR-0100)."
  application_id = scaleway_iam_application.ci_drill.id

  rule {
    project_ids          = [var.drill_project_id]
    permission_set_names = ["InstancesFullAccess", "ObjectStorageFullAccess"]
  }

  # Drill DNS records live in the prod project's zone. Scaleway cannot scope
  # DNS permissions to a single zone, so this grants DNS in the whole prod project.
  rule {
    project_ids          = [var.prod_project_id]
    permission_set_names = ["DomainsDNSFullAccess"]
  }

  rule {
    organization_id      = var.scaleway_organization_id
    permission_set_names = ["IAMManager"]
  }
}

resource "scaleway_iam_api_key" "ci_drill" {
  application_id     = scaleway_iam_application.ci_drill.id
  description        = "GitHub environment drill: restore drill terraform (ADR-0100)"
  default_project_id = var.drill_project_id
  expires_at         = local.key_expires_at

  lifecycle {
    ignore_changes = [expires_at]
  }
}

# --------------------------------------------------------------- ci-plan
# Read-only identity for PR plans (GitHub environment prod-plan, which is not
# gated by reviewers and is reachable from PR branches).
resource "scaleway_iam_application" "ci_plan" {
  name        = "budget-planner-ci-plan"
  description = "Read-only CI identity for prod PR plans (GitHub environment prod-plan). ADR-0100."
}

resource "scaleway_iam_policy" "ci_plan" {
  name           = "budget-planner-ci-plan"
  description    = "Read-only on the prod project and IAM, for terraform plan (ADR-0100)."
  application_id = scaleway_iam_application.ci_plan.id

  rule {
    project_ids          = [var.prod_project_id]
    permission_set_names = ["InstancesReadOnly", "ObjectStorageReadOnly", "DomainsDNSReadOnly"]
  }

  rule {
    organization_id      = var.scaleway_organization_id
    permission_set_names = ["IAMReadOnly"]
  }
}

resource "scaleway_iam_api_key" "ci_plan" {
  application_id     = scaleway_iam_application.ci_plan.id
  description        = "GitHub environment prod-plan: terraform plan, read-only (ADR-0100)"
  default_project_id = var.prod_project_id
  expires_at         = local.key_expires_at

  lifecycle {
    ignore_changes = [expires_at]
  }
}

# ------------------------------------------------------ state bucket policies
# Allow-list semantics (ADR-0091): anything not allowed is denied; no Deny
# statements. Always include the admin principals to avoid locking out the operator.
locals {
  drill_state_policy = {
    Version = "2023-04-17"
    Statement = [
      {
        Sid       = "AllowCiDrill"
        Effect    = "Allow"
        Principal = { SCW = ["application_id:${scaleway_iam_application.ci_drill.id}"] }
        Action    = local.state_rw_actions
        Resource  = [var.drill_state_bucket, "${var.drill_state_bucket}/*"]
      },
      {
        Sid       = "AllowStateAdmins"
        Effect    = "Allow"
        Principal = { SCW = var.state_admin_principals }
        Action    = ["s3:*"]
        Resource  = [var.drill_state_bucket, "${var.drill_state_bucket}/*"]
      },
    ]
  }

  prod_state_policy = {
    Version = "2023-04-17"
    Statement = [
      {
        Sid       = "AllowCiProd"
        Effect    = "Allow"
        Principal = { SCW = ["application_id:${scaleway_iam_application.ci_prod.id}"] }
        Action    = local.state_rw_actions
        Resource  = [var.prod_state_bucket, "${var.prod_state_bucket}/*"]
      },
      {
        # Plan reads state and may only write the lock object.
        Sid       = "AllowCiPlanRead"
        Effect    = "Allow"
        Principal = { SCW = ["application_id:${scaleway_iam_application.ci_plan.id}"] }
        Action    = local.state_ro_actions
        Resource  = [var.prod_state_bucket, "${var.prod_state_bucket}/*"]
      },
      {
        Sid       = "AllowCiPlanLock"
        Effect    = "Allow"
        Principal = { SCW = ["application_id:${scaleway_iam_application.ci_plan.id}"] }
        Action    = ["s3:PutObject", "s3:DeleteObject"]
        Resource  = ["${var.prod_state_bucket}/prod/terraform.tfstate.tflock"]
      },
      {
        Sid       = "AllowStateAdmins"
        Effect    = "Allow"
        Principal = { SCW = var.state_admin_principals }
        Action    = ["s3:*"]
        Resource  = [var.prod_state_bucket, "${var.prod_state_bucket}/*"]
      },
    ]
  }
}

resource "scaleway_object_bucket_policy" "tfstate_drill" {
  bucket     = var.drill_state_bucket
  region     = var.region
  project_id = var.drill_project_id
  policy     = jsonencode(local.drill_state_policy)
}

resource "scaleway_object_bucket_policy" "tfstate_prod" {
  count = var.restrict_prod_state_bucket ? 1 : 0

  bucket     = var.prod_state_bucket
  region     = var.region
  project_id = var.prod_project_id
  policy     = jsonencode(local.prod_state_policy)
}
