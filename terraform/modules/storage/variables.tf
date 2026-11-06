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
