output "policy_json" {
  description = "Bucket policy document (JSON)."
  value       = jsonencode(local.policy)
}
