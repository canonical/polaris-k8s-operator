# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import pytest
from ops.pebble import Layer, ServiceStatus
from ops.testing import Container, Context, Exec, Model, Mount, PeerRelation, Relation

from charm import PolarisK8sCharm
from core.constants import (
    METASTORE_RELATION_NAME,
    PEERS_RELATION_NAME,
    POLARIS_APPLICATION_PROPERTIES,
    POLARIS_BOOTSTRAP_COMMAND,
    POLARIS_CONTAINER_NAME,
    POLARIS_SERVICE_NAME,
    S3_RELATION_NAME,
)


@pytest.fixture
def polaris_context() -> Context:
    """Provide fixture for scenario context based on the polaris charm."""
    return Context(charm_type=PolarisK8sCharm)


@pytest.fixture
def model() -> Model:
    """Provide fixture for the testing Juju model."""
    return Model(name="test-model")


@pytest.fixture
def polaris_peers_relation() -> PeerRelation:
    """Provide fixture for the Polaris peer relation."""
    return PeerRelation(
        endpoint=PEERS_RELATION_NAME,
        interface="polaris-peers",
    )


@pytest.fixture
def polaris_container(tmp_path: Path) -> Container:
    """Provide fixture for the Polaris workload container."""
    return Container(
        name=POLARIS_CONTAINER_NAME,
        can_connect=True,
        mounts={"polaris": Mount(location="/etc/polaris", source=tmp_path)},
        execs=[Exec(list(POLARIS_BOOTSTRAP_COMMAND))],
        service_statuses={POLARIS_SERVICE_NAME: ServiceStatus.ACTIVE},
        layers={
            POLARIS_SERVICE_NAME: Layer(
                {
                    "services": {
                        POLARIS_SERVICE_NAME: {
                            "override": "merge",
                            "startup": "enabled",
                            "on-failure": "restart",
                            "environment": {
                                "QUARKUS_CONFIG_LOCATIONS": (
                                    f"file://{POLARIS_APPLICATION_PROPERTIES}"
                                )
                            },
                        }
                    }
                }
            )
        },
    )


@pytest.fixture
def metastore_relation() -> Relation:
    return Relation(
        endpoint=METASTORE_RELATION_NAME,
        interface="postgresql_client",
        remote_app_name="metastore",
        local_app_data={
            "database": "polaris",
        },
        remote_app_data={
            "database": "polaris",
            "endpoints": "postgresql-k8s-primary:5432",
            "username": "polaris",
            "password": "pwd",
        },
    )


@pytest.fixture
def s3_relation():
    return Relation(
        endpoint=S3_RELATION_NAME,
        interface="s3",
        remote_app_name="s3-integrator",
        local_app_data={"bucket": "catalog"},
        remote_app_data={
            "access-key": "access-key",
            "bucket": "my-bucket",
            "data": '{"bucket": "catalog"}',
            "endpoint": "https://s3.endpoint",
            "path": "spark-events",
            "secret-key": "secret-key",
            "region": "us-east-1",
        },
    )
