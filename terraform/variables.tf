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
# Computed locals derived from inputs (surfaced through outputs).
# ----------------------------------------------------------------------------

locals {
  subdomain = var.env == "prod" ? var.subdomain_prod : var.subdomain_drill
  fqdn      = "${local.subdomain}.${var.domain}"

  name_prefix = "budget-planner-${var.env}"
  bucket_name = "${local.name_prefix}-${var.scaleway_region}"
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
