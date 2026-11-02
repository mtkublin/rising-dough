# Non-human identity for cloud-init + Litestream.
# ADR-0035 §3: least-privilege, scoped to the project.
resource "scaleway_iam_application" "app" {
  name        = "${var.name_prefix}-app"
  description = "Non-human IAM identity for ${var.name_prefix} (Litestream + first-boot pulls)."
}

resource "scaleway_iam_policy" "object_storage" {
  name           = "${var.name_prefix}-object-storage"
  description    = "Grants object-storage read/write within the ${var.name_prefix} project only."
  application_id = scaleway_iam_application.app.id

  rule {
    project_ids          = [var.scaleway_project_id]
    permission_set_names = ["ObjectStorageFullAccess"]
  }
}

resource "scaleway_iam_api_key" "app" {
  application_id = scaleway_iam_application.app.id
  description    = "API key consumed by Litestream on the ${var.name_prefix} VM."

  # Rotate by `terraform apply -replace='module.iam.scaleway_iam_api_key.app'`.
}
