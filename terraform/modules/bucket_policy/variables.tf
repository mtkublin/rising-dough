variable "bucket_name" {
  description = "Name of the bucket the policy is attached to."
  type        = string
}

variable "env_application_id" {
  description = "IAM application id of this env (Litestream identity). Granted the minimal read/write set."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.env_application_id))
    error_message = "env_application_id must be a UUID."
  }
}

variable "admin_principals" {
  description = "Operator principals with full access, each 'user_id:<uuid>' or 'application_id:<uuid>'."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for p in var.admin_principals : can(regex("^(user|application)_id:[0-9a-f-]{36}$", p))])
    error_message = "Each admin principal must look like 'user_id:<uuid>' or 'application_id:<uuid>'."
  }
}

variable "readonly_principals" {
  description = "Principals with read-only access (prod: the restore key's application), each 'user_id:<uuid>' or 'application_id:<uuid>'."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for p in var.readonly_principals : can(regex("^(user|application)_id:[0-9a-f-]{36}$", p))])
    error_message = "Each read-only principal must look like 'user_id:<uuid>' or 'application_id:<uuid>'."
  }
}
