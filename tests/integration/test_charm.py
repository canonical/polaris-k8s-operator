# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import yaml
from apache_polaris.sdk.management.models.create_principal_request import CreatePrincipalRequest
from apache_polaris.sdk.management.models.principal import Principal

from core.constants import ADMIN_USER

from .helpers import S3Info, polaris_management_api, set_s3_credentials
from .supporting_charms import SingleVariantCharmVersion

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("metadata.yaml").read_text())
APP_NAME = METADATA["name"]

SECRET_NAME = "admin-password"
TEST_PASSWORD = "s3cr3t"
UPDATED_TEST_PASSWORD = "n3w-s3cr3t"

RESTORED_APP_NAME = "polaris-k8s-restored"
RESTORED_SECRET_NAME = "restored-admin-password"

PRINCIPAL_NAME = "restoration-check"


def test_deploy(juju: jubilant.Juju, polaris_charm: Path) -> None:
    """Deploy polaris."""
    resources = {"polaris-image": METADATA["resources"]["polaris-image"]["upstream-source"]}
    juju.deploy(polaris_charm, app="polaris-k8s", resources=resources)
    logger.info("Waiting for polaris to be idle...")
    juju.wait(jubilant.all_blocked, delay=5)


def test_deploy_s3_integrator(
    juju: jubilant.Juju, s3: SingleVariantCharmVersion, s3_credentials: S3Info
) -> None:
    """Test deploying the s3-integrator charm and configuring it."""
    juju.deploy(**s3.to_dict())

    endpoint_url = s3_credentials["endpoint"]
    access_key = s3_credentials["access_key"]
    secret_key = s3_credentials["secret_key"]
    bucket_name = s3_credentials["bucket"]
    path = s3_credentials["path"]
    region = s3_credentials["region"]
    juju.config(
        s3.app,
        {"bucket": bucket_name, "path": path, "endpoint": endpoint_url, "region": region},
    )
    set_s3_credentials(juju, s3.app, access_key, secret_key)
    logger.info("Waiting for s3-integrator to be idle...")
    juju.wait(lambda status: jubilant.all_active(status, s3.app), delay=5)
    juju.integrate(APP_NAME, s3.app)


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


def test_update_admin_password_while_metastore_detached(
    juju: jubilant.Juju, metastore: SingleVariantCharmVersion
) -> None:
    """Update the admin password while the metastore relation is broken."""
    juju.remove_relation(APP_NAME, metastore.app)
    logger.info("Waiting for polaris to be blocked...")
    juju.wait(lambda status: jubilant.all_blocked(status, APP_NAME), delay=15)

    logger.info("Updating the admin password while polaris is blocked...")
    juju.update_secret(SECRET_NAME, {f"{ADMIN_USER}": UPDATED_TEST_PASSWORD})
    juju.wait(lambda status: jubilant.all_blocked(status, APP_NAME), delay=15)

    juju.integrate(APP_NAME, metastore.app)
    logger.info("Waiting for polaris to be active...")
    juju.wait(jubilant.all_active, delay=15)


def test_polaris_api_is_reachable_updated_secret_password(juju: jubilant.Juju) -> None:
    """Interact with polaris using the password updated while the metastore was detached."""
    api = polaris_management_api(juju, client_secret=UPDATED_TEST_PASSWORD)
    principals = api.list_principals()
    assert len(principals.principals) == 1
    assert principals.principals[0].client_id == ADMIN_USER


def test_create_principal(juju: jubilant.Juju) -> None:
    """Create a principal to verify the metastore content survives a redeploy."""
    api = polaris_management_api(juju, client_secret=UPDATED_TEST_PASSWORD)
    api.create_principal(CreatePrincipalRequest(principal=Principal(name=PRINCIPAL_NAME)))

    principals = api.list_principals()
    assert len(principals.principals) == 2
    assert PRINCIPAL_NAME in {principal.name for principal in principals.principals}


def test_scale_units_ok(juju: jubilant.Juju) -> None:
    """Scale polaris to 3 units."""
    juju.add_unit(APP_NAME, num_units=2)
    juju.wait(jubilant.all_active, delay=5)


def test_deploy_new_instance_with_existing_metastore(
    juju: jubilant.Juju,
    polaris_charm: Path,
    metastore: SingleVariantCharmVersion,
    s3: SingleVariantCharmVersion,
) -> None:
    """Deploy a new polaris instance against the already bootstrapped metastore.

    The system-user secret must be configured from the first reconcile, before the
    charm generates its own password.
    """
    juju.remove_application(APP_NAME)
    logger.info("Waiting for the previous polaris instance to be removed...")
    juju.wait(lambda status: APP_NAME not in status.apps, delay=5)

    resources = {"polaris-image": METADATA["resources"]["polaris-image"]["upstream-source"]}
    secret_uri = juju.add_secret(RESTORED_SECRET_NAME, {f"{ADMIN_USER}": UPDATED_TEST_PASSWORD})
    juju.deploy(
        polaris_charm,
        app=RESTORED_APP_NAME,
        resources=resources,
        config={"system-user": secret_uri},
    )
    juju.grant_secret(secret_uri, RESTORED_APP_NAME)

    juju.integrate(RESTORED_APP_NAME, s3.app)
    juju.integrate(RESTORED_APP_NAME, metastore.app)
    logger.info("Waiting for the new polaris instance to be active...")
    # The full credential reconciliation runs on the next update-status event.
    juju.wait(lambda status: jubilant.all_active(status, RESTORED_APP_NAME), delay=15, timeout=900)


def test_new_instance_api_is_reachable_with_existing_password(juju: jubilant.Juju) -> None:
    """Interact with the new polaris instance using the password from the metastore."""
    api = polaris_management_api(juju, app=RESTORED_APP_NAME, client_secret=UPDATED_TEST_PASSWORD)
    principals = api.list_principals()
    assert len(principals.principals) == 2
    assert PRINCIPAL_NAME in {principal.name for principal in principals.principals}
    assert ADMIN_USER in {principal.client_id for principal in principals.principals}
