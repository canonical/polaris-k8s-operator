# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import logging
from pathlib import Path

import httpx2
import jubilant
import pyarrow as pa
import yaml
from apache_polaris.sdk.management import (
    AddGrantRequest,
    AwsStorageConfigInfo,
    CatalogGrant,
    CatalogPrivilege,
    CatalogProperties,
    CreateCatalogRequest,
    PolarisCatalog,
)
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import LongType, NestedField, StringType

from core.constants import CONSOLE_PORT, CONSOLE_TLS_PORT, REALM, ROOT_PRINCIPAL_ID

from .helpers import (
    S3Info,
    admin_password_from_internal_secret,
    polaris_base_url,
    polaris_management_api,
    set_s3_credentials,
)
from .supporting_charms import SingleVariantCharmVersion

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CATALOG_NAME = "storage_test"
NAMESPACE = "default"
TABLE_NAME = "storage_table"
CATALOG_ADMIN_ROLE = "catalog_admin"


def test_deploy(
    juju: jubilant.Juju,
    polaris_charm: Path,
    metastore: SingleVariantCharmVersion,
    s3: SingleVariantCharmVersion,
    s3_credentials: S3Info,
    tls_provider: SingleVariantCharmVersion,
) -> None:
    """Deploy Polaris with its mandatory integrations and a TLS provider."""
    resources = {
        "polaris-image": METADATA["resources"]["polaris-image"]["upstream-source"],
        "polaris-console-image": METADATA["resources"]["polaris-console-image"]["upstream-source"],
    }
    juju.deploy(polaris_charm, app=APP_NAME, resources=resources)
    juju.deploy(**s3.to_dict())
    ca_chain = (
        base64.b64encode(Path(s3_credentials["ca_bundle_path"]).read_bytes()).decode()
        if s3_credentials["ca_bundle_path"]
        else ""
    )
    juju.config(
        s3.app,
        {
            "bucket": s3_credentials["bucket"],
            "path": s3_credentials["path"],
            "endpoint": s3_credentials["endpoint"],
            "region": s3_credentials["region"],
            "tls-ca-chain": ca_chain,
        },
    )
    set_s3_credentials(
        juju,
        s3.app,
        s3_credentials["access_key"],
        s3_credentials["secret_key"],
    )
    juju.deploy(**metastore.to_dict())
    juju.deploy(**tls_provider.to_dict())

    logger.info("Waiting for s3-integrator, metastore and TLS provider to be active...")
    juju.wait(
        lambda status: jubilant.all_active(status, s3.app, metastore.app, tls_provider.app),
        delay=15,
    )

    juju.integrate(APP_NAME, s3.app)
    juju.integrate(APP_NAME, metastore.app)
    juju.integrate(f"{APP_NAME}:client-certificates", tls_provider.app)

    logger.info("Waiting for Polaris to be active...")
    juju.wait(jubilant.all_active, delay=15)


def test_console_serves_https(juju: jubilant.Juju) -> None:
    """Check that the console serves HTTPS when certificates are related."""
    base_url = polaris_base_url(juju, port=CONSOLE_TLS_PORT)
    response = httpx2.get(f"{base_url}/health", verify=False)
    response.raise_for_status()


def test_polaris_management_api_is_reachable_over_https(
    juju: jubilant.Juju, s3_credentials: S3Info
) -> None:
    """Check that Polaris is reachable through the HTTPS-terminated console."""
    api = polaris_management_api(juju, port=CONSOLE_TLS_PORT, verify_ssl=False)

    principals = api.list_principals()
    assert len(principals.principals) == 1
    assert principals.principals[0].client_id == ROOT_PRINCIPAL_ID

    base_location = f"s3://{s3_credentials['bucket']}/{s3_credentials['path']}/{CATALOG_NAME}"
    api.create_catalog(
        CreateCatalogRequest(
            catalog=PolarisCatalog(
                type="INTERNAL",
                name=CATALOG_NAME,
                properties=CatalogProperties(default_base_location=base_location),
                storage_config_info=AwsStorageConfigInfo(
                    storage_type="S3",
                    allowed_locations=[base_location],
                    region=s3_credentials["region"],
                    endpoint=s3_credentials["endpoint"],
                    endpoint_internal=s3_credentials["endpoint"],
                    path_style_access=True,
                    kms_unavailable=True,
                    sts_unavailable=True,
                ),
            )
        )
    )
    assert api.get_catalog(CATALOG_NAME).name == CATALOG_NAME

    # Note: turns out that the catalog admin cannot create tables by default.
    # TODO(client): investigate if we need to adapt the charm logic so that we can
    # create catalogs for client integrations.
    api.add_grant_to_catalog_role(
        CATALOG_NAME,
        CATALOG_ADMIN_ROLE,
        AddGrantRequest(
            grant=CatalogGrant(type="catalog", privilege=CatalogPrivilege.TABLE_WRITE_DATA)
        ),
    )


def test_polaris_catalog_write_read_over_https(
    juju: jubilant.Juju,
    s3_credentials: S3Info,
    monkeypatch,
) -> None:
    """Write and read Iceberg data through Polaris over HTTPS using direct S3 credentials."""
    # The PyIceberg client must trust the object storage CA and receive static S3 keys,
    # because this scenario uses direct, non-vended object storage access.
    monkeypatch.setenv("AWS_CA_BUNDLE", s3_credentials["ca_bundle_path"])
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3_credentials["access_key"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3_credentials["secret_key"])
    monkeypatch.setenv("AWS_DEFAULT_REGION", s3_credentials["region"])
    monkeypatch.setenv("AWS_REGION", s3_credentials["region"])
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)

    base_url = polaris_base_url(juju, port=CONSOLE_TLS_PORT)

    catalog = load_catalog(
        "polaris",
        **{
            "type": "rest",
            "uri": f"{base_url}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": f"{ROOT_PRINCIPAL_ID}:{admin_password_from_internal_secret(juju)}",
            "oauth2-server-uri": f"{base_url}/api/catalog/v1/oauth/tokens",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": REALM,
            "header.X-Iceberg-Access-Delegation": "",  # Important!!
            "ssl": {"cabundle": False},
            # Note: this makes pyiceberg use s3fs/botocore, thus respecting AWS_CA_BUNDLE.
            # Otherwise, we would have to trust the CA at the system level (easy to do in
            # a spread test, but inconvenient for local testing)
            "py-io-impl": "pyiceberg.io.fsspec.FsspecFileIO",
            "s3.endpoint": s3_credentials["endpoint"],
            "s3.region": s3_credentials["region"],
        },
    )

    catalog.create_namespace(NAMESPACE)

    identifier = (NAMESPACE, TABLE_NAME)
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=True),
        NestedField(field_id=2, name="name", field_type=StringType(), required=False),
    )
    table = catalog.create_table(identifier, schema=schema)
    table.append(
        pa.Table.from_pylist(
            [{"id": 1, "name": "one"}],
            schema=pa.schema(
                [
                    pa.field("id", pa.int64(), nullable=False),
                    pa.field("name", pa.string()),
                ]
            ),
        )
    )

    assert table.scan().to_arrow().to_pylist() == [{"id": 1, "name": "one"}]


def test_console_no_longer_serves_http(juju: jubilant.Juju) -> None:
    """Check that the console no longer serves HTTP once TLS is enabled."""
    base_url = polaris_base_url(juju, port=CONSOLE_PORT)
    try:
        response = httpx2.get(f"{base_url}/health")
    except httpx2.HTTPError:
        return

    assert response.is_error
