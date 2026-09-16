terraform {
  required_version = ">= 1.5"
  required_providers {
    juju = {
      source  = "juju/juju"
      version = ">= 1.0"
    }
  }
}


variable "model" {
  type = string
}

variable "postgresql_offer_url" {
  type = string
}

variable "traefik_route_offer_url" {
  type = string
}

resource "juju_model" "iam" {
  name = var.model
}

module "iam" {
  source                  = "git::https://github.com/canonical/iam-bundle-integration?ref=v1.1.1"
  model                   = juju_model.iam.uuid
  postgresql_offer_url    = var.postgresql_offer_url
  traefik_route_offer_url = var.traefik_route_offer_url
}
