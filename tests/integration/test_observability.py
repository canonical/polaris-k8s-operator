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
COS_LITE_TF = Path.cwd() / "tests/integration/resources/cos-lite/main.tf"
LOKI = "loki"
PROMETHEUS = "prometheus"
GRAFANA = "grafana"


def get_grafana_access(juju: jubilant.Juju) -> tuple[str, str]:
    """Get Grafana URL and password."""
    task = juju.run("grafana/0", "get-admin-password")
    assert task.return_code == 0
    return task.results["url"], task.results["admin-password"]


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


def test_deploy_cos(juju: jubilant.Juju, tf_manager: TfDirManager) -> None:
    """Deploy COS lite."""
    tf_manager.init(str(COS_LITE_TF))
    tf_manager.apply(model=juju.model)
    logger.info("Waiting for all applications to be active...")
    juju.wait(jubilant.all_active, delay=15)


def test_integrate_polaris_cos(juju: jubilant.Juju) -> None:
    """Integrate Polaris with COS lite."""
    juju.integrate(APP_NAME, "loki")
    juju.integrate(APP_NAME, "prometheus")
    juju.integrate(APP_NAME, "grafana")
    logger.info("Waiting for all applications to be all idle...")
    status = juju.wait(jubilant.all_agents_idle, delay=15)

    logger.info("Checking logs in loki")
    loki_address = status.apps[LOKI].units[f"{LOKI}/0"].address

    for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(10), reraise=True):
        with attempt:
            response = httpx2.get(f"http://{loki_address}:3100/loki/api/v1/label/juju_unit/values")
            response.raise_for_status()

            labels = response.json().get("data", [])
            assert f"{APP_NAME}/0" in labels

    loki_query = {"query": f'{{juju_unit="{APP_NAME}/0"}}'}
    data = urlencode(loki_query)
    for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(10), reraise=True):
        with attempt:
            response = httpx2.get(f"http://{loki_address}:3100/loki/api/v1/query_range?{data}")
            response.raise_for_status()

            assert response.json().get("data", {}).get("result", []), "No loki logs found"

    logger.info("Checking metrics in prometheus")
    prometheus_address = status.apps[PROMETHEUS].units[f"{PROMETHEUS}/0"].address
    prom_query = {"query": f'up{{juju_unit="{APP_NAME}/0"}}'}
    params = urlencode(prom_query)

    for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(10), reraise=True):
        with attempt:
            response = httpx2.get(f"http://{prometheus_address}:9090/api/v1/query?{params}")
            response.raise_for_status()

            payload = response.json()
            results = payload.get("data", {}).get("result", [])

            assert len(results) > 0, "No metric series found"

            metric_value = results[0].get("value", [])[1]
            assert metric_value == "1"

    logger.info("Checking dashboard in grafana")
    grafana_address, pw = get_grafana_access(juju)
    for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(10), reraise=True):
        with attempt:
            response = httpx2.get(
                f"{grafana_address}/api/search?query=&starred=false", auth=("admin", pw)
            )
            response.raise_for_status()

            payload = response.json()
            assert any(board["title"] == "Apache Polaris Metrics" for board in payload)
