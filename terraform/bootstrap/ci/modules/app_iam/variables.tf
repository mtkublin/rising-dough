variable "name_prefix" {
  description = "Resource name prefix (e.g. 'budget-planner-prod')."
  type        = string
}

variable "scaleway_project_id" {
  description = "Scaleway project id this IAM scope applies to."
  type        = string
}
