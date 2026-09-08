# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import logging
from pathlib import Path

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

from core.constants import ADMIN_USER, REALM

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
) -> None:
    """Deploy Polaris with metastore and object storage integrations."""
    resources = {"polaris-image": METADATA["resources"]["polaris-image"]["upstream-source"]}
    juju.deploy(polaris_charm, app=APP_NAME, resources=resources)
    logger.info("Waiting for Polaris to block before mandatory integrations are related...")

    juju.deploy(**s3.to_dict())
    ca_chain = base64.b64encode(Path(s3_credentials["ca_bundle_path"]).read_bytes()).decode()
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

    logger.info("Waiting for s3-integrator and metastore to be active...")
    juju.wait(lambda status: jubilant.all_active(status, s3.app, metastore.app), delay=15)

    juju.integrate(APP_NAME, s3.app)
    juju.integrate(APP_NAME, metastore.app)

    logger.info("Waiting for all applications to be active...")
    juju.wait(jubilant.all_active, delay=15)


def test_polaris_catalog_write_read(
    juju: jubilant.Juju,
    s3_credentials: S3Info,
    monkeypatch,
) -> None:
    """Write and read Iceberg data through Polaris using vended S3 credentials."""
    assert s3_credentials["role_arn"]
    assert s3_credentials["user_arn"]

    api = polaris_management_api(juju)
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
                    role_arn=s3_credentials["role_arn"],
                    user_arn=s3_credentials["user_arn"],
                    region=s3_credentials["region"],
                    endpoint=s3_credentials["endpoint"],
                    sts_endpoint=s3_credentials["endpoint"],
                    endpoint_internal=s3_credentials["endpoint"],
                    path_style_access=True,
                    kms_unavailable=True,
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

    # The PyIceberg client can trust the object storage CA, but must not receive static S3 keys.
    #
    monkeypatch.setenv("AWS_CA_BUNDLE", s3_credentials["ca_bundle_path"])
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)

    base_url = polaris_base_url(juju)
    catalog = load_catalog(
        "polaris",
        **{
            "type": "rest",
            "uri": f"{base_url}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": f"{ADMIN_USER}:{admin_password_from_internal_secret(juju)}",
            "oauth2-server-uri": f"{base_url}/api/catalog/v1/oauth/tokens",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": REALM,
            "header.X-Iceberg-Access-Delegation": "vended-credentials",
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
