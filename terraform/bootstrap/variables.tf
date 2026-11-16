variable "scaleway_project_id" {
  description = "Scaleway project id that owns the state bucket."
  type        = string
}

variable "scaleway_organization_id" {
  description = "Scaleway organization id."
  type        = string
}

variable "bucket_name" {
  description = "Name of the Terraform remote-state bucket (must match terraform/envs/*/backend.hcl)."
  type        = string
  default     = "budget-planner-tfstate-pl-waw"
}

variable "region" {
  description = "Scaleway region of the state bucket."
  type        = string
  default     = "pl-waw"
}
