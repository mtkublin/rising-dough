output "bucket_name" {
  description = "Name of the durability bucket."
  value       = scaleway_object_bucket.durability.name
}

output "endpoint_url" {
  description = "S3-compatible endpoint URL for the bucket's region."
  value       = "https://s3.${var.scaleway_region}.scw.cloud"
}

output "bucket_region" {
  description = "Region holding the durability bucket."
  value       = var.scaleway_region
}
