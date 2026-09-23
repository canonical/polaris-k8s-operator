# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
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
    CreateCatalogRoleRequest,
    CreatePrincipalRoleRequest,
    PolarisCatalog,
)
from apache_polaris.sdk.management.models.catalog_role import CatalogRole
from apache_polaris.sdk.management.models.create_principal_request import CreatePrincipalRequest
from apache_polaris.sdk.management.models.grant_catalog_role_request import (
    GrantCatalogRoleRequest,
)
from apache_polaris.sdk.management.models.grant_principal_role_request import (
    GrantPrincipalRoleRequest,
)
from apache_polaris.sdk.management.models.principal import Principal
from apache_polaris.sdk.management.models.principal_role import PrincipalRole
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import LongType, NestedField, StringType

from core.constants import CONSOLE_PORT, REALM, ROOT_PRINCIPAL_ID
from events.oauth import OAuthStatuses

from .helpers import (
    S3Info,
    TfDirManager,
    admin_password_from_internal_secret,
    polaris_base_url,
    polaris_management_api,
    set_s3_credentials,
)
from .supporting_charms import SingleVariantCharmVersion

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("metadata.yaml").read_text())
APP_NAME = METADATA["name"]
IAM_TF = Path.cwd() / "tests/integration/resources/iam/main.tf"
IAM_MODEL = "iam"
OAUTH_SCOPE = ["openid", "profile", "email", "offline_access"]
CATALOG_NAME = "oauth_test"
NAMESPACE = "default"
TABLE_NAME = "oauth_table"
CATALOG_READER_ROLE = "oidc_reader"
OIDC_PRINCIPAL_ROLE = "oidc_user"


def test_deploy(
    juju: jubilant.Juju,
    polaris_charm: Path,
    metastore: SingleVariantCharmVersion,
    s3: SingleVariantCharmVersion,
    s3_credentials: S3Info,
) -> None:
    """Deploy Polaris with metastore and object storage integrations."""
    resources = {
        "polaris-image": METADATA["resources"]["polaris-image"]["upstream-source"],
        "polaris-console-image": METADATA["resources"]["polaris-console-image"]["upstream-source"],
    }
    juju.deploy(polaris_charm, app=APP_NAME, resources=resources)

    juju.deploy(**s3.to_dict())
    juju.config(
        s3.app,
        {
            "bucket": s3_credentials["bucket"],
            "path": s3_credentials["path"],
            "endpoint": s3_credentials["endpoint"],
            "region": s3_credentials["region"],
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


def test_deploy_iam(
    juju: jubilant.Juju,
    ingress: SingleVariantCharmVersion,
    metastore: SingleVariantCharmVersion,
    tls_provider: SingleVariantCharmVersion,
    tf_manager: TfDirManager,
) -> None:
    """Deploy Identity bundle and the additional components needed."""
    juju.deploy(**ingress.to_dict())
    juju.deploy(**tls_provider.to_dict())
    juju.wait(
        lambda status: jubilant.all_active(status, ingress.app, tls_provider.app),
        delay=5,
    )
    juju.integrate(f"{ingress.app}:certificates", f"{tls_provider.app}:certificates")
    juju.integrate(APP_NAME, ingress.app)
    juju.wait(
        lambda status: jubilant.all_active(status, ingress.app, tls_provider.app),
        delay=5,
    )

    juju.offer(metastore.app, endpoint="database")
    juju.offer(ingress.app, endpoint="traefik-route")

    tf_manager.init(str(IAM_TF))
    tf_manager.apply(
        model="iam",
        postgresql_offer_url=f"admin/{juju.model}.{metastore.app}",
        traefik_route_offer_url=f"admin/{juju.model}.{ingress.app}",
    )

    iam_juju = jubilant.Juju(model=IAM_MODEL)
    logger.info("Waiting for all identity applications to be active...")
    iam_juju.wait(jubilant.all_active, delay=15, timeout=600)


def test_integrate_iam(
    juju: jubilant.Juju,
    tls_provider: SingleVariantCharmVersion,
    s3_credentials: S3Info,
) -> None:
    """Integrate Polaris with the identity platform and set up catalog.

    Notes:
    - The terraform bundle creates a "admin/iam.oauth-offer" offer
    - We use a single TLS provider and ingress for Polaris and Hydra. But we still need Polaris
      to trust the CA even if is used by Polaris' very own ingress. Hence, the second relation
      on receive-ca-certs.
    """
    juju.integrate(APP_NAME, f"admin/{IAM_MODEL}.oauth-offer")

    status = juju.wait(lambda status: jubilant.all_blocked(status, APP_NAME), delay=30)
    app_status = status.apps[APP_NAME].app_status
    assert OAuthStatuses.OAUTH_PROVIDER_UNREACHABLE.message in app_status.message

    juju.integrate(f"{APP_NAME}:receive-ca-certs", tls_provider.app)
    juju.wait(jubilant.all_active, delay=30, successes=5)

    admin_api = polaris_management_api(juju)

    base_location = f"s3://{s3_credentials['bucket']}/{s3_credentials['path']}/{CATALOG_NAME}"
    admin_api.create_catalog(
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
    admin_api.create_principal_role(
        CreatePrincipalRoleRequest(principalRole=PrincipalRole(name=OIDC_PRINCIPAL_ROLE))
    )
    admin_api.create_catalog_role(
        CATALOG_NAME,
        CreateCatalogRoleRequest(catalogRole=CatalogRole(name=CATALOG_READER_ROLE)),
    )
    for privilege in (
        CatalogPrivilege.CATALOG_READ_PROPERTIES,
        CatalogPrivilege.NAMESPACE_READ_PROPERTIES,
        CatalogPrivilege.TABLE_READ_DATA,
    ):
        admin_api.add_grant_to_catalog_role(
            CATALOG_NAME,
            CATALOG_READER_ROLE,
            AddGrantRequest(grant=CatalogGrant(type="catalog", privilege=privilege)),
        )

    admin_api.assign_catalog_role_to_principal_role(
        OIDC_PRINCIPAL_ROLE,
        CATALOG_NAME,
        GrantCatalogRoleRequest(catalogRole=CatalogRole(name=CATALOG_READER_ROLE)),
    )
    base_url = polaris_base_url(juju, app=APP_NAME, port=CONSOLE_PORT)
    internal_catalog = load_catalog(
        "polaris",
        **{
            "type": "rest",
            "uri": f"{base_url}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": f"{ROOT_PRINCIPAL_ID}:{admin_password_from_internal_secret(juju)}",
            "oauth2-server-uri": f"{base_url}/api/catalog/v1/oauth/tokens",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": REALM,
            "header.X-Iceberg-Access-Delegation": "",
            "ssl": {"cabundle": False},
            "s3.access-key-id": s3_credentials["access_key"],
            "s3.secret-access-key": s3_credentials["secret_key"],
            "s3.path-style-access": "true",
            "s3.endpoint": s3_credentials["endpoint"],
            "s3.region": s3_credentials["region"],
        },
    )
    internal_catalog.create_namespace(NAMESPACE)
    identifier = (NAMESPACE, TABLE_NAME)
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=True),
        NestedField(field_id=2, name="name", field_type=StringType(), required=False),
    )
    table = internal_catalog.create_table(identifier, schema=schema)
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


def test_oauth_external_user(
    juju: jubilant.Juju,
    ingress: SingleVariantCharmVersion,
    s3_credentials: S3Info,
) -> None:
    """Read a table through Polaris using an externally created Hydra client."""
    iam_juju = jubilant.Juju(model=IAM_MODEL)
    task = iam_juju.run(
        "hydra/leader",
        "create-oauth-client",
        params={
            "grant-types": ["client_credentials"],
            "scope": OAUTH_SCOPE,
            "token-endpoint-auth-method": "client_secret_post",
        },
        wait=60,
    )
    client_id = task.results["client-id"]
    client_secret = task.results["client-secret"]
    admin_api = polaris_management_api(juju)

    admin_api.create_principal(CreatePrincipalRequest(principal=Principal(name=client_id)))
    admin_api.assign_principal_role(
        client_id,
        GrantPrincipalRoleRequest(principalRole=PrincipalRole(name=OIDC_PRINCIPAL_ROLE)),
    )
    identifier = (NAMESPACE, TABLE_NAME)
    base_url = polaris_base_url(juju, app=APP_NAME, port=CONSOLE_PORT)

    task = juju.run(f"{ingress.app}/0", "show-proxied-endpoints")
    assert task.return_code == 0
    hydra_base_url = json.loads(task.results["proxied-endpoints"])[ingress.app]["url"]

    external_catalog = load_catalog(
        "polaris",
        **{
            "type": "rest",
            "uri": f"{base_url}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": f"{client_id}:{client_secret}",
            "oauth2-server-uri": f"{hydra_base_url}/oauth2/token",
            "scope": " ".join(OAUTH_SCOPE),
            "header.Polaris-Realm": REALM,
            "header.X-Iceberg-Access-Delegation": "",
            "ssl": {"cabundle": False},
            "s3.access-key-id": s3_credentials["access_key"],
            "s3.secret-access-key": s3_credentials["secret_key"],
            "s3.path-style-access": "true",
            "s3.endpoint": s3_credentials["endpoint"],
            "s3.region": s3_credentials["region"],
        },
    )
    assert external_catalog.load_table(identifier).scan().to_arrow().to_pylist() == [
        {"id": 1, "name": "one"}
    ]


def test_remove_ingress_oauth_blocked(
    juju: jubilant.Juju, ingress: SingleVariantCharmVersion
) -> None:
    """Removing the Polaris <-> Ingress relation blocks the charm.

    On the ground that OAuth requires it.
    """
    juju.remove_relation(APP_NAME, ingress.app)
    status = juju.wait(jubilant.all_agents_idle, delay=10)
    app_status = status.apps[APP_NAME].app_status
    assert app_status.current == "blocked"
    assert OAuthStatuses.OAUTH_REQUIRES_INGRESS.message in app_status.message


def test_remove_external_oauth(
    juju: jubilant.Juju, tls_provider: SingleVariantCharmVersion
) -> None:
    """Removing the Polaris <-> OAuth integration still results in a functioning charm."""
    juju.remove_relation(APP_NAME, "oauth-offer")
    juju.remove_relation(f"{APP_NAME}:receive-ca-certs", tls_provider.app)

    juju.wait(jubilant.all_active, delay=30)
    admin_api = polaris_management_api(juju)

    assert admin_api.list_principals()
