# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import pytest
from ops.testing import Container, Context, Model, Mount, PeerRelation

from charm import PolarisK8sCharm
from core.constants import (
    PEERS_RELATION_NAME,
    POLARIS_CONTAINER_NAME,
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
    )
