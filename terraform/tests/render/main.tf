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

module "compute" {
  source = "../../modules/compute"

  name_prefix       = "render-check"
  scaleway_zone     = "pl-waw-2"
  app_image_tag     = "render-check"
  hostname          = "render-check.example.invalid"
  bucket_name       = "render-check-bucket"
  bucket_endpoint   = "https://s3.pl-waw.scw.cloud"
  bucket_region     = "pl-waw"
  scw_access_key    = "SCWDUMMYACCESSKEY0000"
  scw_secret_key    = "00000000-dummy-0000-0000-000000000000" # pragma: allowlist secret
  operator_ssh_pub  = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAADUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMM operator-dummy"
  deploy_ssh_pub    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAADUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMM deploy-dummy"
  ghcr_pull_pat     = "ghp_DUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY"
  github_owner      = "render-check-owner"
  admin_email       = "admin@example.invalid"
  admin_password    = "dummy-admin-password" # pragma: allowlist secret
  cookie_secret     = "dummy-cookie-secret"  # pragma: allowlist secret
  trusted_hosts_csv = "render-check.example.invalid"

  tailscale_authkey  = "tskey-auth-DUMMY" # pragma: allowlist secret
  tailscale_hostname = "render-check"
  tailscale_tag      = "tag:drill"

  break_glass_ssh_cidrs = var.break_glass_ssh_cidrs
  console_password_hash = var.console_password_hash

  enable_restore_helper  = var.enable_restore_helper
  restore_source_bucket  = "render-check-prod-bucket"
  scw_access_key_restore = var.enable_restore_helper ? "SCWDUMMYRESTOREKEY000" : ""
  scw_secret_key_restore = var.enable_restore_helper ? "11111111-dummy-0000-0000-000000000000" : ""

  litestream_age_identity  = "AGE-SECRET-KEY-1DUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY"
  litestream_age_recipient = "age1dummydummydummydummydummydummydummydummydummydummydummydummydum"
  backup_max_age_days      = 37
}

output "cloud_init_is_sensitive" {
  description = "Whether scaleway_instance_server.app.cloud_init is marked sensitive (T-D83)."
  value       = module.compute.cloud_init_is_sensitive
}

output "user_data" {
  description = "Rendered cloud-init user-data (contains dummy secrets only)."
  value       = module.compute.user_data
  sensitive   = true
}
