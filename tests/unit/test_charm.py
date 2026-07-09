# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path
from unittest.mock import patch

import ops
import yaml
from ops.testing import Container, Context, PeerRelation, Secret, State

from core.constants import (
    ADMIN_USER,
    PEERS_RELATION_NAME,
    POLARIS_APPLICATION_PROPERTIES,
    POLARIS_CONTAINER_NAME,
    RANDOM_KEY_SIZE,
    SYMMETRIC_KEY,
    SYSTEM_USER_SECRET_LABEL_SUFFIX,
)
from core.statuses import CharmStatuses
from events.polaris import SYSTEM_USER_SECRET_LABEL

CONFIG = yaml.safe_load(Path("./config.yaml").read_text())
ACTIONS = yaml.safe_load(Path("./actions.yaml").read_text())
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

USER_SECRET_ID = "secret:abcdefghijklmnopqrst"
USER_PASSWORD = "supers3cr3t"
UPDATED_USER_PASSWORD = "s3cr3t"
INTERNAL_SYSTEM_USER_SECRET_LABEL = (
    f"{PEERS_RELATION_NAME}.polaris-k8s.app.{SYSTEM_USER_SECRET_LABEL_SUFFIX}"
)


def _bootstrap_credentials_line(config: str) -> str:
    for line in config.splitlines():
        if line.startswith("polaris.bootstrap.credentials="):
            return line
    raise AssertionError("polaris.bootstrap.credentials not found")


def test_start_polaris(polaris_context: Context) -> None:
    # Given
    state = State(
        config={},
        containers=[Container(name=POLARIS_CONTAINER_NAME, can_connect=False)],
    )

    # When
    out = polaris_context.run(polaris_context.on.install(), state)

    # Then
    assert out.unit_status.message == CharmStatuses.WAITING_PEBBLE.value.message


def test_bare_leader_deployment_writes_config_with_random_password(
    polaris_container: Container,
    polaris_context: Context,
    polaris_peers_relation: PeerRelation,
    tmp_path: Path,
) -> None:
    # Given
    state = State(
        config={},
        leader=True,
        relations=[polaris_peers_relation],
        containers=[polaris_container],
    )

    # When
    out = polaris_context.run(polaris_context.on.pebble_ready(polaris_container), state)

    # Then
    config = (tmp_path / Path(POLARIS_APPLICATION_PROPERTIES).name).read_text()
    credentials = _bootstrap_credentials_line(config)
    password = credentials.rsplit(",", maxsplit=1)[1]

    assert credentials.startswith(f"polaris.bootstrap.credentials=POLARIS,{ADMIN_USER},")
    assert password
    assert len(password) == RANDOM_KEY_SIZE * 2
    assert "polaris.authentication.token-broker.type=symmetric-key" in config
    assert (tmp_path / Path(SYMMETRIC_KEY).name).read_text()

    relation = out.get_relation(polaris_peers_relation)
    assert relation.local_app_data.get("shared-key")
    # Note: we do not really care about the actual number, what matters is that
    # it changes so that non-leader units get notified to check the secret.
    assert relation.local_app_data.get("epoch") == "2"


def test_config_changed_uses_configured_system_user_secret(
    polaris_container: Container,
    polaris_context: Context,
    polaris_peers_relation: PeerRelation,
    tmp_path: Path,
) -> None:
    # Given
    user_secret = Secret(
        {ADMIN_USER: USER_PASSWORD},
        id=USER_SECRET_ID,
    )
    state = State(
        config={"system-user": USER_SECRET_ID},
        leader=True,
        relations=[polaris_peers_relation],
        containers=[polaris_container],
        secrets=[user_secret],
    )

    # When
    out = polaris_context.run(polaris_context.on.config_changed(), state)

    # Then
    config = (tmp_path / Path(POLARIS_APPLICATION_PROPERTIES).name).read_text()

    assert f"polaris.bootstrap.credentials=POLARIS,{ADMIN_USER},{USER_PASSWORD}" in config
    assert out.get_secret(id=USER_SECRET_ID).label == SYSTEM_USER_SECRET_LABEL

    relation = out.get_relation(polaris_peers_relation)
    assert relation.local_app_data.get("epoch") == "2"


def test_config_changed_switches_from_random_password_to_user_secret(
    polaris_container: Container,
    polaris_context: Context,
    polaris_peers_relation: PeerRelation,
    tmp_path: Path,
) -> None:
    # Given
    initial_state = State(
        config={},
        leader=True,
        relations=[polaris_peers_relation],
        containers=[polaris_container],
    )
    initial_out = polaris_context.run(
        polaris_context.on.pebble_ready(polaris_container),
        initial_state,
    )
    initial_config = (tmp_path / Path(POLARIS_APPLICATION_PROPERTIES).name).read_text()
    initial_password = _bootstrap_credentials_line(initial_config).rsplit(",", maxsplit=1)[1]

    user_secret = Secret(
        {ADMIN_USER: USER_PASSWORD},
        id=USER_SECRET_ID,
    )
    configured_state = State(
        config={"system-user": USER_SECRET_ID},
        leader=True,
        relations=initial_out.relations,
        containers=initial_out.containers,
        secrets=[*initial_out.secrets, user_secret],
    )

    # When
    out = polaris_context.run(polaris_context.on.config_changed(), configured_state)

    # Then
    config = (tmp_path / Path(POLARIS_APPLICATION_PROPERTIES).name).read_text()

    assert initial_password
    assert initial_password != USER_PASSWORD
    assert f"polaris.bootstrap.credentials=POLARIS,{ADMIN_USER},{USER_PASSWORD}" in config

    relation = out.get_relation(polaris_peers_relation)
    assert relation.local_app_data.get("epoch") == "3"


def test_secret_changed_updates_leader_config_and_epoch(
    polaris_container: Container,
    polaris_context: Context,
    polaris_peers_relation: PeerRelation,
    tmp_path: Path,
) -> None:
    # Given
    user_secret = Secret(
        {ADMIN_USER: USER_PASSWORD},
        latest_content={ADMIN_USER: UPDATED_USER_PASSWORD},
        id=USER_SECRET_ID,
        label=SYSTEM_USER_SECRET_LABEL,
    )
    state = State(
        config={"system-user": USER_SECRET_ID},
        leader=True,
        relations=[polaris_peers_relation],
        containers=[polaris_container],
        secrets=[user_secret],
    )

    # When
    out = polaris_context.run(polaris_context.on.secret_changed(user_secret), state)

    # Then
    config = (tmp_path / Path(POLARIS_APPLICATION_PROPERTIES).name).read_text()

    assert f"polaris.bootstrap.credentials=POLARIS,{ADMIN_USER},{UPDATED_USER_PASSWORD}" in config

    relation = out.get_relation(polaris_peers_relation)
    assert relation.local_app_data.get("epoch") == "2"


def test_configured_system_user_secret_not_found_sets_blocked_status(
    polaris_container: Container,
    polaris_context: Context,
    polaris_peers_relation: PeerRelation,
) -> None:
    # Given
    state = State(
        config={"system-user": USER_SECRET_ID},
        leader=True,
        relations=[polaris_peers_relation],
        containers=[polaris_container],
    )

    # When
    out = polaris_context.run(polaris_context.on.config_changed(), state)

    # Then
    assert out.unit_status.message == CharmStatuses.SYSTEM_USER_SECRET_DOES_NOT_EXIST.value.message


def test_configured_system_user_secret_without_grant_sets_blocked_status(
    polaris_container: Container,
    polaris_context: Context,
    polaris_peers_relation: PeerRelation,
) -> None:
    # Given
    state = State(
        config={"system-user": USER_SECRET_ID},
        leader=True,
        relations=[polaris_peers_relation],
        containers=[polaris_container],
    )

    # When
    with polaris_context(polaris_context.on.config_changed(), state) as manager:
        with patch.object(
            manager.charm.model,
            "get_secret",
            side_effect=ops.ModelError("ERROR permission denied"),
        ):
            out = manager.run()

    # Then
    assert (
        out.unit_status.message
        == CharmStatuses.SYSTEM_USER_SECRET_INSUFFICIENT_PERMISSION.value.message
    )


def test_configured_system_user_secret_with_invalid_content_sets_blocked_status(
    polaris_container: Container,
    polaris_context: Context,
    polaris_peers_relation: PeerRelation,
) -> None:
    # Given
    user_secret = Secret(
        {"invalid-key": USER_PASSWORD},
        id=USER_SECRET_ID,
    )
    state = State(
        config={"system-user": USER_SECRET_ID},
        leader=True,
        relations=[polaris_peers_relation],
        containers=[polaris_container],
        secrets=[user_secret],
    )

    # When
    out = polaris_context.run(polaris_context.on.config_changed(), state)

    # Then
    assert out.unit_status.message == CharmStatuses.SYSTEM_USER_SECRET_INVALID.value.message


def test_non_leader_updates_config_from_internal_peer_secret_on_relation_changed(
    polaris_container: Container,
    polaris_context: Context,
    tmp_path: Path,
) -> None:
    # Given
    relation = PeerRelation(
        endpoint=PEERS_RELATION_NAME,
        interface="polaris-peers",
        local_app_data={
            "shared-key": "shared-key-value",
            "epoch": "2",
        },
        peers_data={1: {}},
    )
    internal_secret = Secret(
        {"charmed-operator-password": UPDATED_USER_PASSWORD},
        label=INTERNAL_SYSTEM_USER_SECRET_LABEL,
        owner="app",
    )
    state = State(
        config={},
        leader=False,
        relations=[relation],
        containers=[polaris_container],
        secrets=[internal_secret],
    )

    # When
    polaris_context.run(polaris_context.on.relation_changed(relation), state)

    # Then
    config = (tmp_path / Path(POLARIS_APPLICATION_PROPERTIES).name).read_text()

    assert f"polaris.bootstrap.credentials=POLARIS,{ADMIN_USER},{UPDATED_USER_PASSWORD}" in config
    assert (tmp_path / Path(SYMMETRIC_KEY).name).read_text() == "shared-key-value"
