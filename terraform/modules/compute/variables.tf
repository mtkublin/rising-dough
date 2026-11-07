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

# T-D56 / ADR-0078 section 3: Litestream replica age encryption.
variable "litestream_age_identity" {
  description = "age private identity (AGE-SECRET-KEY-1... line or the full age-keygen file) written to /etc/budget-planner/litestream-age.key (0600). Used by restores only."
  type        = string
  sensitive   = true
}

variable "litestream_age_recipient" {
  description = "age public recipient (age1...) the replica is encrypted to; must match litestream_age_identity (age-keygen -y)."
  type        = string
}

# T-D57 / ADR-0078 section 4: single source of truth is the root variable
# backup_max_age_days; it is passed to the app as BUDGET_BACKUP_MAX_AGE_DAYS.
variable "backup_max_age_days" {
  description = "Maximum age in days of any copy of user data (ADR-0078 section 4); exported to the app container."
  type        = number
  default     = 37
}

# T-D67 / ADR-0094: Tailscale join (SSH/admin only).
variable "tailscale_authkey" {
  description = "Single-use, pre-authorized Tailscale auth key (tag-bound). Written to a 0600 tmpfs file, consumed by `tailscale up --auth-key=file:...`, then deleted."
  type        = string
  sensitive   = true
}

variable "tailscale_hostname" {
  description = "Tailnet hostname (MagicDNS name) of the VM, e.g. budget-planner-prod."
  type        = string
}

variable "tailscale_tag" {
  description = "Tailscale ACL tag the node advertises, e.g. tag:prod. Must match the tag baked into the auth key."
  type        = string

  validation {
    condition     = can(regex("^tag:[a-z][a-z0-9-]*$", var.tailscale_tag))
    error_message = "tailscale_tag must look like tag:<name>."
  }
}

variable "break_glass_ssh_cidrs" {
  description = "Drill-only, temporary: CIDRs allowed public TCP 22 (security group + host ufw) to debug a failed first boot (T-D81, ADR-0094). Empty = no port 22."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for c in var.break_glass_ssh_cidrs : can(cidrhost(c, 0))])
    error_message = "Every break_glass_ssh_cidrs entry must be a valid CIDR."
  }
}

variable "console_password_hash" {
  description = "Drill-only, temporary (T-D84, ADR-0094): bcrypt hash set as the operator's password so the Scaleway serial console works. Empty = operator stays lock_passwd. Hash only, never plaintext."
  type        = string
  default     = ""
  sensitive   = true
}

variable "boot_log_upload" {
  description = "Drill-only, temporary (T-D86, ADR-0094): bootcmd starts a detached uploader that pushes boot diagnostics to s3://<bucket>/boot-logs/. Reuses the bucket write credential already in user-data."
  type        = bool
  default     = false
}
