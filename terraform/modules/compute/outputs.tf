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
  value       = sha256(local.cloud_init_rendered)
}

output "user_data_is_sensitive" {
  description = "True when the server's user_data attribute carries the sensitive mark (T-D83 test hook; not a secret)."
  value       = issensitive(scaleway_instance_server.app.user_data)
}

output "user_data" {
  description = "Rendered cloud-init payload (contains secrets). Consumed only by the offline render check (T-D77)."
  value       = local.cloud_init_rendered
  sensitive   = true
}

output "host_config" {
  description = "Rendered bp-config document (contains secrets). Test hook for the render check (ADR-0111)."
  value       = local.host_config_json
  sensitive   = true
}

output "host_config_generation" {
  description = "Generation the host agent reports in status.json once converged (ADR-0111)."
  value       = local.host_config_generation
}

output "app_image_ref" {
  description = "Full app image ref (repo:tag@digest) the host is told to run."
  value       = local.host_config_body.image.ref
}

output "server_tags" {
  description = "Tags set on the app server (T-D90 test hook; not a secret)."
  value       = scaleway_instance_server.app.tags
}

output "public_web_rules" {
  description = "Public inbound web rules of the security group (empty on a tailnet-only drill, ADR-0101; test hook, not a secret)."
  value       = local.public_web_rules
}

output "server_type" {
  description = "Scaleway instance type of the VM (T-D123)."
  value       = scaleway_instance_server.app.type
}

output "root_volume_type" {
  description = "Root volume type of the VM (T-D143, ADR-0118; test hook)."
  value       = scaleway_instance_server.app.root_volume[0].volume_type
}

output "root_volume_size_gb" {
  description = "Root volume size in GB (T-D143, ADR-0118; test hook)."
  value       = scaleway_instance_server.app.root_volume[0].size_in_gb
}

output "allow_empty_db" {
  description = "Whether litestream-restore may start an empty database (T-D144, ADR-0119; test hook, not a secret)."
  value       = var.allow_empty_db
}
