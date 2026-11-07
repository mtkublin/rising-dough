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
