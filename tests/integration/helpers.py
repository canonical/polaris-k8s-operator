# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration test helpers for Apache Polaris."""

import os
import shlex
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

import httpx2
import jubilant
import yaml
from apache_polaris.cli.api_client_builder import ApiClientBuilder
from apache_polaris.cli.constants import DEFAULT_HEADER
from apache_polaris.sdk.management import ApiClient, Configuration, rest
from apache_polaris.sdk.management.api import PolarisDefaultApi

from core.constants import (
    ADMIN_USER,
    CONSOLE_PORT,
    CONSOLE_TLS_PORT,
    PEERS_RELATION_NAME,
    REALM,
    SYSTEM_USER_SECRET_LABEL_SUFFIX,
)

METADATA = yaml.safe_load(Path("metadata.yaml").read_text())
APP_NAME = METADATA["name"]

INTERNAL_ADMIN_PASSWORD_KEY = f"{ADMIN_USER}-password"

S3Info = TypedDict(
    "S3Info",
    {
        "endpoint": str,
        "access_key": str,
        "secret_key": str,
        "region": str,
        "bucket": str,
        "path": str,
        "ca_bundle_path": str,
        "role_arn": str,
        "user_arn": str,
    },
)


def polaris_base_url(
    juju: jubilant.Juju,
    app: str = APP_NAME,
    port: int = CONSOLE_PORT,
) -> str:
    """Return the base URL for the Polaris REST API."""
    status = juju.status()
    address = status.apps[app].address

    if not address:
        # Fallback to the first unit address if Juju does not expose an app address.
        address = next(iter(status.apps[app].units.values())).address

    scheme = "https" if port == CONSOLE_TLS_PORT else "http"
    return f"{scheme}://{address}:{port}"


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
    parsed = urlparse(base_url)
    options = Namespace(
        proxy=None,
        access_token=None,
        profile=None,
        base_url=None,
        catalog_url=None,
        host=parsed.hostname,
        port=parsed.port,
        client_id=client_id,
        client_secret=client_secret,
        realm=realm,
        header=header,
        scheme=parsed.scheme,
    )
    return ApiClientBuilder(options).get_api_client()


def polaris_management_api(
    juju: jubilant.Juju,
    *,
    app: str = APP_NAME,
    client_id: str = ADMIN_USER,
    client_secret: str | None = None,
    realm: str = REALM,
    port: int = CONSOLE_PORT,
    verify_ssl: bool = True,
) -> PolarisDefaultApi:
    """Return an authenticated Polaris management API object."""
    password = client_secret or admin_password_from_internal_secret(juju, app)
    base_url = polaris_base_url(juju, app, port=port)

    if not verify_ssl:
        # Note: unfortunately, the polaris sdk does not provide an easy way of
        # disabling tls verification. Even with the verify_ssl=False configuration
        # below, the initial request to get the authentication tokens still goes through
        # tls verification, hence why we do it manually here.
        response = httpx2.post(
            f"{base_url}/api/catalog/v1/oauth/tokens",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": password,
                "scope": "PRINCIPAL_ROLE:ALL",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                DEFAULT_HEADER: realm,
            },
            verify=False,
        )
        response.raise_for_status()
        configuration = Configuration(
            host=f"{base_url}/api/management/v1",
            access_token=response.json()["access_token"],
        )
        configuration.verify_ssl = False
        api_client = ApiClient(configuration, header_name=DEFAULT_HEADER, header_value=realm)
        api_client.rest_client = rest.RESTClientObject(api_client.configuration)
        return PolarisDefaultApi(api_client)

    api_client = polaris_api_client(
        base_url,
        client_id=client_id,
        client_secret=password,
        realm=realm,
    )
    return PolarisDefaultApi(api_client)


def set_s3_credentials(
    juju: jubilant.Juju,
    s3_app_name: str,
    access_key: str,
    secret_key: str,
) -> None:
    """Set s3 credentials using the Juju secret pattern."""
    params = {
        "access-key": access_key,
        "secret-key": secret_key,
    }
    secret_uri = juju.add_secret("s3-credentials", params)
    juju.grant_secret(secret_uri, s3_app_name)
    juju.config(s3_app_name, {"credentials": secret_uri})


class TfDirManager:
    """Taken from https://github.com/canonical/observability-stack."""

    def __init__(self, base_tmpdir):
        self.base: str = str(base_tmpdir)
        self.dir: str = ""

    @property
    def tf_cmd(self):
        return f"terraform -chdir={self.dir}"

    def init(self, tf_file: str):
        """Initialize a Terraform module in a subdirectory."""
        self.dir = os.path.join(self.base, "terraform")
        os.makedirs(self.dir, exist_ok=True)
        shutil.copy(tf_file, os.path.join(self.dir, "main.tf"))
        subprocess.run(shlex.split(f"{self.tf_cmd} init -upgrade"), check=True)

    @staticmethod
    def _args_str(target: str | None = None, **kwargs) -> str:
        target_arg = f"-target module.{target}" if target else ""
        var_args = " ".join(f"-var {k}={v}" for k, v in kwargs.items())
        return "-auto-approve " + f"{target_arg} " + var_args

    def apply(self, target: str | None = None, **kwargs):
        cmd_str = f"{self.tf_cmd} apply " + self._args_str(target, **kwargs)
        subprocess.run(shlex.split(cmd_str), check=True)

    def destroy(self, **kwargs):
        cmd_str = f"{self.tf_cmd} destroy " + self._args_str(None, **kwargs)
        subprocess.run(shlex.split(cmd_str), check=True)
