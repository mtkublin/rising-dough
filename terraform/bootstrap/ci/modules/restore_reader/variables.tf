variable "name_prefix" {
  description = "Resource name prefix (e.g. 'budget-planner-prod')."
  type        = string
}

variable "scaleway_project_id" {
  description = "Prod project id; the read-only grant is scoped to it."
  type        = string
}
