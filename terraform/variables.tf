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
  default     = "pl-waw-1"
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
  description = "When true, Terraform owns the DNS zone on Scaleway DNS. When false, zone records only (operator maintains zone elsewhere)."
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
