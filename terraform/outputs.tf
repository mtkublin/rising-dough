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

output "app_image_ref" {
  description = "App image ref `<tag>@sha256:<digest>` the host is told to run (ADR-0111). CI reads it as the next apply's previous ref."
  value       = var.app_image_ref
}

output "app_image_previous_ref" {
  description = "Ref the host ran before the last apply (ADR-0111); the rollback target."
  value       = var.app_image_previous_ref
}

output "host_config_generation" {
  description = "Generation the host agent reports in /.well-known/bp-deploy-status.json once converged (ADR-0111)."
  value       = module.compute.host_config_generation
}

output "host_image_ref" {
  description = "Full image ref (repo:tag@digest) the host agent reports as running once converged (ADR-0111)."
  value       = module.compute.app_image_ref
}

output "ci_ssh_authorized" {
  description = "True when the CI SSH key is authorised on the host (drill only, T-D137). Boolean, not a secret; test hook."
  value       = local.ci_ssh_pubkey_effective != ""
}

output "drill_run_id" {
  description = "Drill only (T-D139, ADR-0116): numeric run id baked into the tailnet name; empty on prod. CI re-applies on an existing drill read it back so the host name does not change."
  value       = var.drill_run_id
}

output "vm_spec_id" {
  description = "Hash of the replacement-forcing VM inputs; part of the Tailscale key description so a new VM gets a new key (T-D155, ADR-0121). Not a secret."
  value       = local.vm_spec_id
}
