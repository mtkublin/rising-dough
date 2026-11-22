terraform {
  required_version = ">= 1.10.0"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.46"
    }
    tailscale = {
      source  = "tailscale/tailscale"
      version = "~> 0.29"
    }
    # T-Q277 / ADR-0135: per-drill Litestream age key pair. Exact pin (supply chain).
    age = {
      source  = "koendelaat/age"
      version = "= 0.1.3"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
