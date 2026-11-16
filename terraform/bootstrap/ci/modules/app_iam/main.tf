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

  # ADR-0092 (amended, T-D74): S3 calls resolve buckets against the key's default
  # project. Pin it to this env's project; otherwise Scaleway falls back to the
  # organization default (the prod project), even for the drill key.
  default_project_id = var.scaleway_project_id

  # Scaleway sets a 1-year default expiry when expires_at is unset. Ignore it so
  # plans stay clean; rotate before it, see runbooks/deploy.md "Rotate the
  # Litestream API key". Read the date from the `scw_app_key_expires_at` output.
  lifecycle {
    ignore_changes = [expires_at]
  }
}
