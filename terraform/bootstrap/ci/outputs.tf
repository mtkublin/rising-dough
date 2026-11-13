# Read with `terraform output -raw <name>` and paste into GitHub environment
# secrets (runbooks/key-rotation.md). Never echo them into logs or commit them.
output "ci_prod_access_key" {
  description = "ci-prod access key id -> GitHub environment prod, secret SCW_ACCESS_KEY."
  value       = scaleway_iam_api_key.ci_prod.access_key
  sensitive   = true
}

output "ci_prod_secret_key" {
  description = "ci-prod secret key -> GitHub environment prod, secret SCW_SECRET_KEY."
  value       = scaleway_iam_api_key.ci_prod.secret_key
  sensitive   = true
}

output "ci_drill_access_key" {
  description = "ci-drill access key id -> GitHub environment drill, secret SCW_ACCESS_KEY."
  value       = scaleway_iam_api_key.ci_drill.access_key
  sensitive   = true
}

output "ci_drill_secret_key" {
  description = "ci-drill secret key -> GitHub environment drill, secret SCW_SECRET_KEY."
  value       = scaleway_iam_api_key.ci_drill.secret_key
  sensitive   = true
}

output "ci_plan_access_key" {
  description = "ci-plan access key id -> GitHub environment prod-plan, secret SCW_ACCESS_KEY."
  value       = scaleway_iam_api_key.ci_plan.access_key
  sensitive   = true
}

output "ci_plan_secret_key" {
  description = "ci-plan secret key -> GitHub environment prod-plan, secret SCW_SECRET_KEY."
  value       = scaleway_iam_api_key.ci_plan.secret_key
  sensitive   = true
}

output "ci_key_expires_at" {
  description = "Intended expiry of the CI keys (not sensitive)."
  value       = scaleway_iam_api_key.ci_prod.expires_at
}

output "ci_application_ids" {
  description = "Application ids (for bucket principals and audits)."
  value = {
    prod  = scaleway_iam_application.ci_prod.id
    drill = scaleway_iam_application.ci_drill.id
    plan  = scaleway_iam_application.ci_plan.id
  }
}

# T-D103 / ADR-0104: env-stack identities. Non-secret ids go to the
# APP_APPLICATION_ID / RESTORE_READER_APPLICATION_ID environment secrets.
output "app_application_ids" {
  description = "Litestream app application ids per env -> GitHub secret APP_APPLICATION_ID."
  value = {
    prod  = module.app_prod.application_id
    drill = module.app_drill.application_id
  }
}

output "restore_reader_application_id" {
  description = "Restore-reader application id -> prod/prod-plan secret RESTORE_READER_APPLICATION_ID."
  value       = module.restore_reader.application_id
}

# An imported key has no secret (Scaleway returns it only at creation): the prod
# values are null until the first rotation; read them once from the prod state
# (runbooks/key-rotation.md part 2).
output "app_prod_access_key" {
  description = "Prod Litestream key id -> prod/prod-plan secret APP_SCW_ACCESS_KEY."
  value       = module.app_prod.access_key
  sensitive   = true
}

output "app_prod_secret_key" {
  description = "Prod Litestream secret -> prod/prod-plan secret APP_SCW_SECRET_KEY (null right after import)."
  value       = module.app_prod.secret_key
  sensitive   = true
}

output "app_drill_access_key" {
  description = "Drill Litestream key id -> drill environments' secret APP_SCW_ACCESS_KEY."
  value       = module.app_drill.access_key
  sensitive   = true
}

output "app_drill_secret_key" {
  description = "Drill Litestream secret -> drill environments' secret APP_SCW_SECRET_KEY."
  value       = module.app_drill.secret_key
  sensitive   = true
}

output "restore_reader_access_key" {
  description = "Restore-reader key id -> drill environments' secret PROD_REPLICA_RO_ACCESS_KEY."
  value       = module.restore_reader.access_key
  sensitive   = true
}

output "restore_reader_secret_key" {
  description = "Restore-reader secret -> PROD_REPLICA_RO_SECRET_KEY (null right after import)."
  value       = module.restore_reader.secret_key
  sensitive   = true
}

# Scaleway sets a 1-year default expiry. Rotate 30 days before (runbooks/deploy.md).
output "app_key_expires_at" {
  description = "Expiry of the Litestream API keys per env."
  value = {
    prod  = module.app_prod.expires_at
    drill = module.app_drill.expires_at
  }
}
