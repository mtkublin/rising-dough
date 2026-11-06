variable "managed_zone" {
  description = "When true, the zone already exists at Scaleway DNS and this env's A/AAAA records are managed in it. Terraform never creates or owns the zone (ADR-0088). When false, nothing is created (operator maintains records elsewhere)."
  type        = bool
}

variable "domain" {
  description = "Root domain (e.g. 'example.com')."
  type        = string
}

variable "subdomain" {
  description = "Subdomain under the root (e.g. 'drill.budget' or 'budget')."
  type        = string
}

variable "instance_ipv4" {
  description = "Public IPv4 address for the A record."
  type        = string
}

variable "instance_ipv6" {
  description = "Public IPv6 address for the AAAA record. Nullable when IPv6 is not attached."
  type        = string
  default     = null
}

variable "record_ttl_secs" {
  description = "DNS record TTL in seconds."
  type        = number
  default     = 300
}
