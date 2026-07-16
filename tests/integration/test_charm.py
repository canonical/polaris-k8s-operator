# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import yaml

from core.constants import ADMIN_USER

from .helpers import polaris_management_api
from .supporting_charms import SingleVariantCharmVersion

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("metadata.yaml").read_text())
APP_NAME = METADATA["name"]

SECRET_NAME = "admin-password"
TEST_PASSWORD = "s3cr3t"


def test_deploy(juju: jubilant.Juju, polaris_charm: Path) -> None:
    """Deploy polaris."""
    resources = {"polaris-image": METADATA["resources"]["polaris-image"]["upstream-source"]}
    juju.deploy(polaris_charm, app="polaris-k8s", resources=resources)
    logger.info("Waiting for polaris to be idle...")
    juju.wait(jubilant.all_blocked, delay=5)


def test_integrate_metastore(juju: jubilant.Juju, metastore: SingleVariantCharmVersion) -> None:
    """Integrate polaris with its metastore."""
    juju.deploy(**metastore.to_dict())
    logger.info("Waiting for metastore app to be active...")
    juju.wait(lambda status: jubilant.all_active(status, metastore.app), delay=15)

    juju.integrate(APP_NAME, metastore.app)
    logger.info("Waiting for polaris to be active...")
    juju.wait(jubilant.all_active, delay=15)


def test_polaris_api_is_reachable_random_passwd(juju: jubilant.Juju) -> None:
    """Interact with polaris using the internal password."""
    api = polaris_management_api(juju)
    principals = api.list_principals()
    assert len(principals.principals) == 1
    assert principals.principals[0].client_id == ADMIN_USER


@pytest.mark.skip(reason="Enable once bootstrap is idempotent")
def test_remove_integration_re_integrate_metastore(
    juju: jubilant.Juju, metastore: SingleVariantCharmVersion
) -> None:
    """Integrate polaris with its metastore."""
    juju.remove_relation(APP_NAME, metastore.app)
    logger.info("Waiting for polaris to be blocked...")
    juju.wait(lambda status: jubilant.all_blocked(status, APP_NAME), delay=15)

    juju.integrate(APP_NAME, metastore.app)
    logger.info("Waiting for polaris to be active...")
    juju.wait(jubilant.all_active, delay=15)


def test_set_admin_password_in_polaris(juju: jubilant.Juju) -> None:
    """Set system-user config option in Polaris."""
    secret_uri = juju.add_secret(SECRET_NAME, {f"{ADMIN_USER}": TEST_PASSWORD})
    juju.grant_secret(secret_uri, APP_NAME)
    juju.config(APP_NAME, {"system-user": secret_uri})
    juju.wait(jubilant.all_active, delay=15)


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
