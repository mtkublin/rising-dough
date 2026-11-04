variable "name_prefix" {
  description = "Resource name prefix (e.g. 'budget-planner-prod')."
  type        = string
}

variable "scaleway_zone" {
  description = "Scaleway zone (e.g. 'pl-waw-2')."
  type        = string
}

variable "instance_type" {
  description = "Scaleway instance type. Stardust1-S is the v3 target (ADR-0032 §1)."
  type        = string
  default     = "STARDUST1-S"
}

variable "image" {
  description = "Scaleway marketplace image slug. Ubuntu 24.04 minimal."
  type        = string
  default     = "ubuntu_noble"
}

variable "app_image_tag" {
  description = "Container image tag to pull on first boot."
  type        = string
}

variable "hostname" {
  description = "FQDN the host answers on (passed into Caddyfile + compose env)."
  type        = string
}

variable "bucket_name" {
  description = "Durability bucket name (Litestream target)."
  type        = string
}

variable "bucket_endpoint" {
  description = "S3-compatible endpoint for the durability bucket."
  type        = string
}

variable "bucket_region" {
  description = "Region holding the durability bucket."
  type        = string
}

variable "scw_access_key" {
  description = "IAM access key for Litestream."
  type        = string
  sensitive   = true
}

variable "scw_secret_key" {
  description = "IAM secret key for Litestream."
  type        = string
  sensitive   = true
}

variable "operator_ssh_pub" {
  description = "Operator's SSH public key (ed25519)."
  type        = string
  sensitive   = true
}

variable "deploy_ssh_pub" {
  description = "GitHub Actions deploy keypair public key."
  type        = string
  sensitive   = true
}

variable "ghcr_pull_pat" {
  description = "GHCR read-only PAT."
  type        = string
  sensitive   = true
}

variable "github_owner" {
  description = "GitHub owner of the container image."
  type        = string
}

variable "admin_email" {
  description = "Bootstrap admin email."
  type        = string
}

variable "admin_password" {
  description = "Bootstrap admin initial password."
  type        = string
  sensitive   = true
}

variable "cookie_secret" {
  description = "Session cookie signing secret."
  type        = string
  sensitive   = true
}

variable "trusted_hosts_csv" {
  description = "Comma-separated list of trusted hosts for the FastAPI TrustedHostMiddleware."
  type        = string
}

variable "enable_restore_helper" {
  description = "Install /usr/local/bin/restore-from-prod and the read-only prod replica credential (drill environment only, T-D41a)."
  type        = bool
  default     = false
}

variable "restore_source_bucket" {
  description = "PROD replica bucket the restore helper reads from (read-only)."
  type        = string
  default     = ""
}

variable "scw_access_key_restore" {
  description = "READ-ONLY access key scoped to the prod replica bucket (GetObject + ListBucket). Drill only."
  type        = string
  default     = ""
  sensitive   = true
}

variable "scw_secret_key_restore" {
  description = "Secret for scw_access_key_restore."
  type        = string
  default     = ""
  sensitive   = true
}
