output "fqdn" {
  description = "Fully-qualified domain name wired by this module."
  value       = "${var.subdomain}.${var.domain}"
}

output "managed_zone" {
  description = "Whether Terraform owns the parent zone."
  value       = var.managed_zone
}
