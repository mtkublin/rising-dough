# ----------------------------------------------------------------------------
# Operator-supplied inputs (declared in envs/<env>/terraform.tfvars).
# ----------------------------------------------------------------------------

variable "env" {
  description = "Deployment environment. One of 'drill' or 'prod'. Drives naming + state key."
  type        = string

  validation {
    condition     = contains(["drill", "prod"], var.env)
    error_message = "env must be either 'drill' or 'prod'."
  }
}

variable "break_glass_ssh_cidrs" {
  description = "Drill-only, temporary: CIDRs allowed public SSH (TCP 22) to debug a failed boot when Tailscale does not come up (T-D81, ADR-0094). Must be empty unless env = drill; remove after debugging."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for c in var.break_glass_ssh_cidrs : can(cidrhost(c, 0))])
    error_message = "Every break_glass_ssh_cidrs entry must be a valid CIDR, e.g. 203.0.113.7/32."
  }

  validation {
    condition     = length(var.break_glass_ssh_cidrs) == 0 || var.env == "drill"
    error_message = "break_glass_ssh_cidrs is drill-only (env must be 'drill')."
  }
}

variable "admin_email" {
  description = "Email address of the bootstrap admin user (ADR-0061 §3). Used by the app's startup bootstrap routine."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.admin_email))
    error_message = "admin_email must be a valid email address."
  }
}

variable "scaleway_project_id" {
  description = "Scaleway project id that owns the resources."
  type        = string
}

variable "scaleway_organization_id" {
  description = "Scaleway organization id."
  type        = string
}

variable "scaleway_region" {
  description = "Scaleway region (pl-waw places compute and storage in Warsaw)."
  type        = string
  default     = "pl-waw"
}

variable "scaleway_zone" {
  description = "Scaleway availability zone within the region."
  type        = string
  default     = "pl-waw-2"
}

variable "domain" {
  description = "Root domain under which the app is reachable (e.g. 'example.com')."
  type        = string
}

variable "subdomain_drill" {
  description = "Subdomain used for the disposable 'drill' environment."
  type        = string
  default     = "drill.budget"
}

variable "subdomain_prod" {
  description = "Subdomain used for the production environment."
  type        = string
  default     = "budget"
}

variable "managed_dns_zone" {
  description = "When true, the domain's zone already exists at Scaleway DNS (Scaleway Domains registration) and this env manages only its own A/AAAA records in it; Terraform never creates the zone (ADR-0088). When false, no DNS resources are created (operator maintains records elsewhere)."
  type        = bool
  default     = false
}

variable "dns_zone_project_id" {
  description = "Scaleway project that owns the DNS zone (the prod project, rising-dough). DNS records of every env are created there, even when the env's own resources live in another project (ADR-0092)."
  type        = string
  default     = "53175dd0-b944-489b-b05d-3f55d65d79af"

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.dns_zone_project_id))
    error_message = "dns_zone_project_id must be a UUID."
  }
}

variable "app_image_tag" {
  description = "Container image tag the host should pull on first boot. Deploy pipeline updates it afterwards."
  type        = string
  default     = "main"
}

variable "operator_ssh_pubkey" {
  description = "Operator's personal SSH public key (ed25519) authorised for the 'operator' sudoer account."
  type        = string
  sensitive   = true
}

variable "github_deploy_pubkey" {
  description = "Public key of the GitHub Actions deploy keypair (ADR-0037). Pinned to the restricted deploy command."
  type        = string
  sensitive   = true
}

variable "ghcr_pull_pat" {
  description = "GHCR read-only PAT used by cloud-init to pull the private container image on first boot."
  type        = string
  sensitive   = true
}

variable "github_owner" {
  description = "GitHub owner (user or org) that hosts the container image repository."
  type        = string
}

# ----------------------------------------------------------------------------
# Bucket policy principals (ADR-0091, T-D68).
# Format: "user_id:<uuid>" (scw iam user list) or "application_id:<uuid>"
# (scw iam application list).
# ----------------------------------------------------------------------------

variable "bucket_admin_principals" {
  description = "Operator principals granted full access to this env's bucket. Needed unless Terraform runs as the Organization owner."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for p in var.bucket_admin_principals : can(regex("^(user|application)_id:[0-9a-f-]{36}$", p))])
    error_message = "Each entry must look like 'user_id:<uuid>' or 'application_id:<uuid>'."
  }
}

variable "bucket_readonly_principals" {
  description = "Read-only principals for this env's bucket. Prod: the application owning the restore key (scw_access_key_restore). Leave empty on drill."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for p in var.bucket_readonly_principals : can(regex("^(user|application)_id:[0-9a-f-]{36}$", p))])
    error_message = "Each entry must look like 'user_id:<uuid>' or 'application_id:<uuid>'."
  }
}

# ----------------------------------------------------------------------------
# Computed locals derived from inputs (surfaced through outputs).
# ----------------------------------------------------------------------------

locals {
  # T-D57 / ADR-0078 section 4: Litestream keeps generations for 720h (30 d, see
  # cloud-init/compose/litestream.yml.tpl); the remainder of the ceiling is
  # the bucket's noncurrent-version expiry (37 - 30 = 7 d by default).
  litestream_retention_days = 30
  lifecycle_days            = var.backup_max_age_days - local.litestream_retention_days

  subdomain = var.env == "prod" ? var.subdomain_prod : var.subdomain_drill
  fqdn      = "${local.subdomain}.${var.domain}"

  name_prefix = "budget-planner-${var.env}"
  bucket_name = "${local.name_prefix}-${var.scaleway_region}"

  tailscale_tag      = "tag:${var.env}"
  tailscale_hostname = "budget-planner-${var.env}" # MagicDNS name used by CI and the operator
}

# ----------------------------------------------------------------------------
# Restore drill (T-D41a, ADR-0034 §5). Only consumed when env == "drill".
# Supplied via TF_VAR_* from the restore-drill workflow; never committed.
# Empty on prod; the helper aborts at runtime if they are empty on a drill host.
# ----------------------------------------------------------------------------

variable "scw_access_key_restore" {
  description = "READ-ONLY access key scoped to the prod replica bucket (GetObject + ListBucket). Drill env only."
  type        = string
  default     = ""
  sensitive   = true
}

variable "scw_secret_key_restore" {
  description = "Secret key paired with scw_access_key_restore."
  type        = string
  default     = ""
  sensitive   = true
}

# ----------------------------------------------------------------------------
# Litestream replica encryption (T-D56, ADR-0078 section 3). Required on every env.
# Generate with `age-keygen -o litestream-age.key`; derive the recipient with
# `age-keygen -y litestream-age.key`. Supply via TF_VAR_* (never committed).
# A lost identity makes the encrypted replica unrecoverable. The drill env gets
# the PROD identity (it restores the prod replica). The committed dev-only
# identity under deploy/ must never be used here.
# ----------------------------------------------------------------------------

variable "litestream_age_identity" {
  description = "age private identity for the Litestream replica (AGE-SECRET-KEY-1... line or the full age-keygen output file). Rendered to /etc/budget-planner/litestream-age.key at 0600."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("AGE-SECRET-KEY-1[0-9A-Z]{50,}", var.litestream_age_identity))
    error_message = "litestream_age_identity must contain an AGE-SECRET-KEY-1... line (from age-keygen)."
  }
}

variable "litestream_age_recipient" {
  description = "age public recipient (age1...) the replica is encrypted to; derive with `age-keygen -y <identity file>`."
  type        = string

  validation {
    condition     = can(regex("^age1[0-9a-z]{58}$", var.litestream_age_recipient))
    error_message = "litestream_age_recipient must be an age public key (age1 + 58 chars), e.g. the output of age-keygen -y."
  }
}

# T-D57 / ADR-0078 section 4: THE knob for the maximum age of any copy of user
# data. Terraform derives the bucket noncurrent-expiry from it; the app's
# BUDGET_BACKUP_MAX_AGE_DAYS (rendered into the compose template) derives the
# pre-migration backup pruning.
variable "backup_max_age_days" {
  description = "Maximum age in days of any copy of user data outside the live DB (ADR-0078 section 4)."
  type        = number
  default     = 37

  validation {
    condition     = var.backup_max_age_days >= 31 && var.backup_max_age_days <= 365
    error_message = "backup_max_age_days must be 31..365 (30 d Litestream retention + at least 1 d noncurrent expiry)."
  }
}

# ----------------------------------------------------------------------------
# Tailscale (T-D67, ADR-0094). SSH/admin access only. Supply via TF_VAR_*
# (never committed). The OAuth client needs scope `auth_keys` (write) and carries
# only tag:automation, which owns tag:prod + tag:drill (ADR-0094 amendment).
# ----------------------------------------------------------------------------

variable "tailscale_oauth_client_id" {
  description = "Tailscale OAuth client ID (scope auth_keys, tag tag:automation)."
  type        = string
  sensitive   = true
}

variable "tailscale_oauth_client_secret" {
  description = "Tailscale OAuth client secret."
  type        = string
  sensitive   = true
}
