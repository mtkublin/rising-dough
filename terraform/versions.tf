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
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
