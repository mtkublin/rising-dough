variable "bucket_name" {
  description = "Name of the durability bucket (Litestream target)."
  type        = string
}

variable "scaleway_region" {
  description = "Scaleway region holding the bucket."
  type        = string
}

variable "lifecycle_days" {
  description = "Days before noncurrent versions are expired (ADR-0078 section 4: 7 d, so 30 d Litestream retention + 7 d = 37 d ceiling)."
  type        = number
  default     = 7
}

variable "log_bucket_suffix" {
  description = "Suffix for the companion access-log bucket. Currently informational only; v3 does not wire bucket logs."
  type        = string
  default     = "logs"
}

variable "env_application_id" {
  description = "IAM application id of this env; the only principal granted read/write by default (ADR-0091)."
  type        = string
}

variable "admin_principals" {
  description = "Operator principals ('user_id:<uuid>' / 'application_id:<uuid>') with full bucket access."
  type        = list(string)
  default     = []
}

variable "readonly_principals" {
  description = "Read-only principals (prod: the restore key's application) (ADR-0091)."
  type        = list(string)
  default     = []
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete a non-empty bucket. true for drill only; keep false for prod."
  type        = bool
  default     = false
}

variable "expire_boot_logs" {
  description = "Drill-only (T-D86, ADR-0094): add a lifecycle rule expiring the boot-logs/ prefix after 7 days. false leaves the bucket unchanged (prod)."
  type        = bool
  default     = false
}
