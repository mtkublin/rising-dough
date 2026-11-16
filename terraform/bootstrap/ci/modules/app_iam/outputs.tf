output "application_id" {
  description = "Scaleway IAM application id."
  value       = scaleway_iam_application.app.id
}

output "access_key" {
  description = "Scaleway IAM access key for the application."
  value       = scaleway_iam_api_key.app.access_key
  sensitive   = true
}

output "secret_key" {
  description = "Scaleway IAM secret key for the application."
  value       = scaleway_iam_api_key.app.secret_key
  sensitive   = true
}

output "expires_at" {
  description = "Expiry of the Litestream API key (Scaleway sets a 1-year default)."
  value       = scaleway_iam_api_key.app.expires_at
}
