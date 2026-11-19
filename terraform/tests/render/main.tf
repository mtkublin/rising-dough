# ----------------------------------------------------------------------------
# T-D77: offline render fixture for the cloud-init user-data.
#
# Calls the REAL compute module (same templatefile() chain as the server, see
# modules/compute/user_data.tf) with obviously fake values, so the rendered
# payload can be linted without a VM boot. No credentials, no API calls: all
# inputs are dummies and the compute module has no data sources.
# Driven by `just tf-render-check` and `terraform test` (render.tftest.hcl).
# ----------------------------------------------------------------------------

provider "scaleway" {
  # Dummy values so the provider configures offline; nothing is ever created.
  access_key = "SCWDUMMYDUMMYDUMMYDU"
  secret_key = "00000000-0000-4000-8000-000000000000"
  project_id = "00000000-0000-4000-8000-000000000000"
  region     = "pl-waw"
  zone       = "pl-waw-2"
}

variable "enable_restore_helper" {
  description = "Render the drill-only restore helper branch."
  type        = bool
  default     = true
}

variable "break_glass_ssh_cidrs" {
  description = "Render the drill-only break-glass ufw rules (T-D81)."
  type        = list(string)
  default     = []
}

variable "console_password_hash" {
  description = "Dummy bcrypt hash for the drill-only console break-glass render (T-D84)."
  type        = string
  default     = ""
}

variable "ci_ssh_pub" {
  description = "CI SSH public key rendered for the operator (T-D137)."
  type        = string
  default     = ""
}

variable "boot_log_upload" {
  description = "Render the drill-only boot log uploader (T-D86)."
  type        = bool
  default     = false
}

variable "tailnet_only" {
  description = "Render the tailnet-only drill variant (ADR-0101): ts.net host, tailscaled socket mount, no port 80."
  type        = bool
  default     = false
}

variable "expires_at" {
  description = "Drill TTL tag (T-D90)."
  type        = string
  default     = ""
}

variable "allow_empty_db" {
  description = "Render the restore service with the empty-DB guard relaxed (T-D156, ADR-0127)."
  type        = bool
  default     = false
}

locals {
  dummy_digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" # pragma: allowlist secret
}

module "compute" {
  source = "../../modules/compute"

  name_prefix       = "render-check"
  scaleway_zone     = "pl-waw-2"
  app_image_ref     = "sha-1234567@sha256:${local.dummy_digest}"
  hostname          = var.tailnet_only ? "budget-planner-drill.tail0000.ts.net" : "render-check.example.invalid"
  bucket_name       = "render-check-bucket"
  bucket_endpoint   = "https://s3.pl-waw.scw.cloud"
  bucket_region     = "pl-waw"
  scw_access_key    = "SCWDUMMYACCESSKEY0000"
  scw_secret_key    = "00000000-dummy-0000-0000-000000000000" # pragma: allowlist secret
  operator_ssh_pub  = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAADUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMM operator-dummy"
  ci_ssh_pub        = var.ci_ssh_pub
  ghcr_pull_pat     = "ghp_DUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY"
  github_owner      = "render-check-owner"
  github_repo       = "render-check-repo"
  admin_email       = "admin@example.invalid"
  admin_password    = "dummy-admin-password" # pragma: allowlist secret
  cookie_secret     = "dummy-cookie-secret"  # pragma: allowlist secret
  trusted_hosts_csv = var.tailnet_only ? "budget-planner-drill.tail0000.ts.net" : "render-check.example.invalid"
  tailnet_only      = var.tailnet_only

  tailscale_authkey  = "tskey-auth-DUMMY" # pragma: allowlist secret
  tailscale_hostname = "render-check"
  tailscale_tag      = "tag:drill"

  break_glass_ssh_cidrs = var.break_glass_ssh_cidrs
  console_password_hash = var.console_password_hash
  boot_log_upload       = var.boot_log_upload
  expires_at            = var.expires_at

  enable_restore_helper  = var.enable_restore_helper
  restore_source_bucket  = "render-check-prod-bucket"
  scw_access_key_restore = var.enable_restore_helper ? "SCWDUMMYRESTOREKEY000" : ""
  scw_secret_key_restore = var.enable_restore_helper ? "11111111-dummy-0000-0000-000000000000" : ""

  litestream_age_identity  = "AGE-SECRET-KEY-1DUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY"
  litestream_age_recipient = "age1dummydummydummydummydummydummydummydummydummydummydummydummydum"
  backup_max_age_days      = 37
  allow_empty_db           = var.allow_empty_db
}

output "user_data_is_sensitive" {
  description = "Whether scaleway_instance_server.app.user_data is marked sensitive (T-D83, ADR-0111)."
  value       = module.compute.user_data_is_sensitive
}

output "host_config" {
  description = "Rendered bp-config document (dummy secrets only; ADR-0111)."
  value       = module.compute.host_config
  sensitive   = true
}

output "host_config_generation" {
  description = "Generation of the rendered bp-config (ADR-0111)."
  value       = module.compute.host_config_generation
}

output "user_data" {
  description = "Rendered cloud-init user-data (contains dummy secrets only)."
  value       = module.compute.user_data
  sensitive   = true
}

output "security_group_rules" {
  description = "Inbound rules of the compute security group (ADR-0101)."
  value       = module.compute.public_web_rules
}

output "server_tags" {
  description = "Compute server tags (T-D90)."
  value       = module.compute.server_tags
}

output "all_rendered" {
  description = "cloud-init plus every agent-managed file, concatenated (dummy secrets only; ADR-0111)."
  value       = join("\n", concat([module.compute.user_data], [for f in jsondecode(module.compute.host_config).files : f.content]))
  sensitive   = true
}
