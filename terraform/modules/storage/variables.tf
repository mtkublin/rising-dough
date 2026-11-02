variable "bucket_name" {
  description = "Name of the durability bucket (Litestream target)."
  type        = string
}

variable "scaleway_region" {
  description = "Scaleway region holding the bucket."
  type        = string
}

variable "lifecycle_days" {
  description = "Number of days before noncurrent versions are expired (ADR-0034 retention = 30d)."
  type        = number
  default     = 30
}

variable "log_bucket_suffix" {
  description = "Suffix for the companion access-log bucket. Currently informational only; v3 does not wire bucket logs."
  type        = string
  default     = "logs"
}
