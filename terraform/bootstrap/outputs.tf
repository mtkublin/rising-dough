output "bucket_name" {
  description = "State bucket name."
  value       = scaleway_object_bucket.tfstate.name
}

output "region" {
  description = "State bucket region."
  value       = var.region
}

output "endpoint" {
  description = "S3-compatible endpoint for the backend configuration."
  value       = "https://s3.${var.region}.scw.cloud"
}
