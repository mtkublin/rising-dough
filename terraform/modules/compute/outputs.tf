output "vm_id" {
  description = "Scaleway instance id."
  value       = scaleway_instance_server.app.id
}

output "vm_ipv4" {
  description = "Flex IPv4 bound to the instance."
  value       = scaleway_instance_ip.ipv4.address
}

output "vm_ipv6" {
  description = "IPv6 address assigned to the instance."
  value       = scaleway_instance_ip.ipv6.address
}

output "security_group_id" {
  description = "Security group id attached to the instance."
  value       = scaleway_instance_security_group.app.id
}

output "user_data_sha256" {
  description = "sha256 of the rendered cloud-init payload. Useful for drift tracking."
  value       = sha256(local.user_data)
}
