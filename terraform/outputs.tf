output "admin_initial_password" {
  description = "One-time admin bootstrap password (ADR-0061 §3). Capture into a password manager and discard — not reconciled on subsequent applies."
  value       = random_password.admin_initial_password.result
  sensitive   = true
}

output "cookie_secret" {
  description = "Session cookie signing secret rendered into the compose env."
  value       = random_password.cookie_secret.result
  sensitive   = true
}

output "console_password" {
  description = "Drill-only (T-D84): operator serial-console password; null unless break_glass_console_password = true. Read with `terraform output -raw console_password`."
  value       = var.break_glass_console_password ? random_password.console[0].result : null
  sensitive   = true
}

output "vm_ipv4" {
  description = "Public IPv4 address of the application VM."
  value       = module.compute.vm_ipv4
}

output "vm_ipv6" {
  description = "Public IPv6 address of the application VM."
  value       = module.compute.vm_ipv6
}

output "bucket_name" {
  description = "Durability bucket name (Litestream target)."
  value       = module.storage.bucket_name
}

output "bucket_endpoint" {
  description = "S3-compatible endpoint for the durability bucket."
  value       = module.storage.endpoint_url
}

output "fqdn" {
  description = "Fully-qualified hostname the app answers on."
  value       = local.fqdn
}

output "scw_access_key" {
  description = "IAM access key scoped to the durability bucket. Used by Litestream only."
  value       = module.iam.access_key
  sensitive   = true
}

# T-D69 / ADR-0092: prod only (null on drill). Store as GitHub `drill`-environment
# secrets PROD_REPLICA_RO_ACCESS_KEY / PROD_REPLICA_RO_SECRET_KEY.
output "restore_reader_access_key" {
  description = "Read-only access key for the prod replica bucket (restore drill). Prod only."
  value       = one(module.restore_reader[*].access_key)
  sensitive   = true
}

output "restore_reader_secret_key" {
  description = "Secret key paired with restore_reader_access_key. Prod only."
  value       = one(module.restore_reader[*].secret_key)
  sensitive   = true
}

output "scw_secret_key" {
  description = "IAM secret key scoped to the durability bucket."
  value       = module.iam.secret_key
  sensitive   = true
}

output "tailscale_hostname" {
  description = "MagicDNS name of the VM on the tailnet (SSH target for CI and the operator; T-D67)."
  value       = local.tailscale_hostname
}

# T-D74 / ADR-0092: Scaleway applies a 1-year default expiry to the Litestream key.
# Rotate before this date (runbooks/deploy.md, operator-checklist F).
output "scw_app_key_expires_at" {
  description = "Expiry of the Litestream IAM API key. Rotate 30 days before."
  value       = module.iam.expires_at
}
