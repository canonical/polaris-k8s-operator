# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration test helpers for Apache Polaris."""

from argparse import Namespace
from pathlib import Path

import jubilant
import yaml
from apache_polaris.cli.api_client_builder import ApiClientBuilder
from apache_polaris.cli.constants import DEFAULT_HEADER
from apache_polaris.sdk.management import ApiClient
from apache_polaris.sdk.management.api import PolarisDefaultApi

from core.constants import (
    ADMIN_USER,
    PEERS_RELATION_NAME,
    REALM,
    REST_PORT,
    SYSTEM_USER_SECRET_LABEL_SUFFIX,
)

METADATA = yaml.safe_load(Path("metadata.yaml").read_text())
APP_NAME = METADATA["name"]

INTERNAL_ADMIN_PASSWORD_KEY = f"{ADMIN_USER}-password"


def polaris_base_url(
    juju: jubilant.Juju,
    app: str = APP_NAME,
    port: int = REST_PORT,
) -> str:
    """Return the base URL for the Polaris REST API."""
    status = juju.status()
    address = status.apps[app].address

    if not address:
        # Fallback to the first unit address if Juju does not expose an app address.
        address = next(iter(status.apps[app].units.values())).address

    return f"http://{address}:{port}"


def internal_user_secret_label(app: str = APP_NAME) -> str:
    """Return the label of the internal peer secret storing system user credentials."""
    return f"{PEERS_RELATION_NAME}.{app}.app.{SYSTEM_USER_SECRET_LABEL_SUFFIX}"


def admin_password_from_internal_secret(
    juju: jubilant.Juju,
    app: str = APP_NAME,
) -> str:
    """Read the charm-generated admin password from the internal Juju secret."""
    secret = juju.show_secret(internal_user_secret_label(app), reveal=True)
    return secret.content[INTERNAL_ADMIN_PASSWORD_KEY]


def polaris_api_client(
    base_url: str,
    *,
    client_id: str = ADMIN_USER,
    client_secret: str,
    realm: str = REALM,
    header: str = DEFAULT_HEADER,
) -> ApiClient:
    """Build an authenticated Apache Polaris management API client."""
    options = Namespace(
        proxy=None,
        access_token=None,
        profile=None,
        base_url=base_url,
        host=None,
        port=None,
        client_id=client_id,
        client_secret=client_secret,
        realm=realm,
        header=header,
    )
    return ApiClientBuilder(options).get_api_client()


def polaris_management_api(
    juju: jubilant.Juju,
    *,
    app: str = APP_NAME,
    client_id: str = ADMIN_USER,
    client_secret: str | None = None,
    realm: str = REALM,
) -> PolarisDefaultApi:
    """Return an authenticated Polaris management API object."""
    password = client_secret or admin_password_from_internal_secret(juju, app)
    api_client = polaris_api_client(
        polaris_base_url(juju, app),
        client_id=client_id,
        client_secret=password,
        realm=realm,
    )
    return PolarisDefaultApi(api_client)
