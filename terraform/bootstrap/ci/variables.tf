variable "scaleway_organization_id" {
  description = "Scaleway organization id (scope of the IAM permission sets)."
  type        = string
}

variable "prod_project_id" {
  description = "Prod/default project id. Holds prod resources, the prod state bucket and the DNS zone used by both envs."
  type        = string
}

variable "drill_project_id" {
  description = "Drill project id."
  type        = string
}

variable "region" {
  description = "Scaleway region of the state buckets."
  type        = string
  default     = "pl-waw"
}

variable "prod_state_bucket" {
  description = "Prod Terraform state bucket (created by ../, ADR-0096)."
  type        = string
  default     = "budget-planner-tfstate-pl-waw"
}

variable "drill_state_bucket" {
  description = "Drill Terraform state bucket (created by ../, ADR-0100)."
  type        = string
  default     = "budget-planner-tfstate-drill-pl-waw"
}

variable "state_admin_principals" {
  description = <<-EOT
    Bucket-policy principals that keep full access to the state buckets
    (break-glass admin), e.g. ["user_id:<uuid>"]. Required: a bucket policy is an
    allow-list (ADR-0091), so an empty list could lock the operator out.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.state_admin_principals) > 0 && alltrue([for p in var.state_admin_principals : can(regex("^(user_id|application_id):", p))])
    error_message = "Provide at least one principal as user_id:<uuid> or application_id:<uuid>."
  }
}

variable "restrict_prod_state_bucket" {
  description = <<-EOT
    Attach the allow-list policy to the EXISTING prod state bucket. Leave false for
    the first apply; set true after the CI keys work (see runbooks/key-rotation.md).
    The drill state bucket always gets its policy (it is new and empty).
  EOT
  type        = bool
  default     = false
}

variable "ci_key_ttl_hours" {
  description = "Lifetime of the CI API keys from apply time (default 1 year). Rotate 30 days before; see runbooks/key-rotation.md."
  type        = number
  default     = 8760
}

variable "ci_prod_iam_transition" {
  description = <<-EOT
    Grant ci-prod IAMReadOnly (ADR-0104 section 4). Keep true until the first prod
    release has applied the `removed` blocks for module.iam / module.restore_reader,
    then set false and re-apply.
  EOT
  type        = bool
  default     = true
}
