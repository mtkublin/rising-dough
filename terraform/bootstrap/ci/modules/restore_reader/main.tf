# Stable read-only identity for the monthly restore drill (T-D69, ADR-0092).
# Lives in the bootstrap/ci state, scoped to the PROD project (ADR-0104). The
# drill env consumes its key via GitHub `drill`-environment secrets; it is also
# listed in prod's bucket policy.
resource "scaleway_iam_application" "restore_reader" {
  name        = "${var.name_prefix}-restore-reader"
  description = "Read-only identity used by the restore drill to read the prod replica (ADR-0092)."
}

resource "scaleway_iam_policy" "restore_reader" {
  name           = "${var.name_prefix}-restore-reader-object-storage"
  description    = "Object Storage read-only within the prod project only."
  application_id = scaleway_iam_application.restore_reader.id

  rule {
    project_ids          = [var.scaleway_project_id]
    permission_set_names = ["ObjectStorageReadOnly"]
  }
}

resource "scaleway_iam_api_key" "restore_reader" {
  application_id = scaleway_iam_application.restore_reader.id
  description    = "Restore-drill read-only key for the prod replica bucket."

  # Scaleway sets a 1-year default expiry when expires_at is unset; expires_at
  # forces replacement, so the imported key (ADR-0104) would be re-created.
  # Rotate before it (runbooks/key-rotation.md cadence table).
  lifecycle {
    ignore_changes = [expires_at]
  }
}
