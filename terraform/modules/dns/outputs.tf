output "fqdn" {
  description = "Fully-qualified domain name wired by this module."
  value       = "${var.subdomain}.${var.domain}"
}

output "managed_zone" {
  description = "Whether this env manages its records in the Scaleway-hosted zone (the zone itself is never owned by Terraform)."
  value       = var.managed_zone
}
