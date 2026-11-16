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

output "tailscale_hostname" {
  description = "MagicDNS name of the VM on the tailnet (SSH target for CI and the operator; T-D67)."
  value       = local.tailscale_hostname
}
