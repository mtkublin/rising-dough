# T-D77: offline render of the real user-data path with mocked providers.
# Run: terraform -chdir=terraform init -backend=false && terraform -chdir=terraform test

mock_provider "scaleway" {}

run "user_data_starts_with_cloud_config" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = startswith(nonsensitive(output.user_data), "#cloud-config\n")
    error_message = "cloud-init ignores user-data unless `#cloud-config` is line 1 (T-D75)."
  }
}

run "user_data_without_restore_helper" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    enable_restore_helper = false
  }

  assert {
    condition     = startswith(nonsensitive(output.user_data), "#cloud-config\n")
    error_message = "cloud-init ignores user-data unless `#cloud-config` is line 1 (T-D75)."
  }
}
