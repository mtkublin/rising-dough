output "application_id" {
  description = "IAM application id (added to the prod bucket policy read-only statement)."
  value       = scaleway_iam_application.restore_reader.id
}

output "access_key" {
  description = "Read-only access key."
  value       = scaleway_iam_api_key.restore_reader.access_key
  sensitive   = true
}

output "secret_key" {
  description = "Read-only secret key."
  value       = scaleway_iam_api_key.restore_reader.secret_key
  sensitive   = true
}
