# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import yaml

from core.constants import ADMIN_USER
from .helpers import polaris_management_api

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("metadata.yaml").read_text())
APP_NAME = METADATA["name"]

SECRET_NAME = "admin-password"
TEST_PASSWORD = "s3cr3t"


def test_deploy(juju: jubilant.Juju, polaris_charm: Path) -> None:
    """Deploy polaris."""
    resources = {"polaris-image": METADATA["resources"]["polaris-image"]["upstream-source"]}
    juju.deploy(polaris_charm, app="polaris-k8s", resources=resources)
    juju.wait(jubilant.all_active, delay=5)


def test_polaris_api_is_reachable_random_passwd(juju: jubilant.Juju) -> None:
    """Interact with polaris using the internal password."""
    api = polaris_management_api(juju)
    principals = api.list_principals()
    assert len(principals.principals) == 1
    assert principals.principals[0].client_id == ADMIN_USER


def test_set_admin_password_in_polaris(juju: jubilant.Juju) -> None:
    """Set system-user config option in Polaris."""
    secret_uri = juju.add_secret(SECRET_NAME, {f"{ADMIN_USER}": TEST_PASSWORD})
    juju.grant_secret(secret_uri, APP_NAME)
    juju.config(APP_NAME, {"system-user": secret_uri})
    juju.wait(jubilant.all_active)


def test_polaris_api_is_reachable_secret_password(juju: jubilant.Juju) -> None:
    """Interact with polaris using the secret password."""
    api = polaris_management_api(juju, client_secret=TEST_PASSWORD)
    principals = api.list_principals()
    assert len(principals.principals) == 1
    assert principals.principals[0].client_id == ADMIN_USER


def test_scale_units_ok(juju: jubilant.Juju) -> None:
    """Scale polaris to 3 units."""
    juju.add_unit(APP_NAME, num_units=2)
    juju.wait(jubilant.all_active, delay=5)
