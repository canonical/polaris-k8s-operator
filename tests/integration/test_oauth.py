# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from urllib.parse import urlencode

import httpx2
import jubilant
import yaml
from tenacity import Retrying, stop_after_attempt, wait_fixed

from .helpers import S3Info, TfDirManager, set_s3_credentials
from .supporting_charms import SingleVariantCharmVersion

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("metadata.yaml").read_text())
APP_NAME = METADATA["name"]
IAM_TF = Path.cwd() / "tests/integration/resources/iam/main.tf"
IAM_MODEL = "iam"


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
    iam_juju.wait(jubilant.all_active, delay=15)
