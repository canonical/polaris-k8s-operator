# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Polaris charm general event handlers."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

import ops
from data_platform_helpers.advanced_statuses.models import StatusObject
from data_platform_helpers.advanced_statuses.protocol import ManagerStatusProtocol
from data_platform_helpers.advanced_statuses.types import Scope
from pydantic import ValidationError

from config.charm import PolarisCharmConfig
from core.constants import (
    ADMIN_USER,
    PEERS_RELATION_NAME,
    POLARIS_CONTAINER_NAME,
    RANDOM_KEY_SIZE,
    REST_PORT,
)
from core.context import Context
from core.logging import WithLogging
from core.statuses import CharmStatuses, ConfigStatuses
from core.workload.polaris import PolarisWorkload
from events import BaseEventHandler
from managers.polaris import PolarisManager

SYSTEM_USER_SECRET_LABEL = "system-user"

if TYPE_CHECKING:
    from charm import PolarisK8sCharm


@dataclass(frozen=True)
class SystemUserSecretValidation:
    """Validation result for the configured system-user secret."""

    configured: bool
    password: str | None = None
    status: StatusObject | None = None


class PolarisEvents(BaseEventHandler, WithLogging, ManagerStatusProtocol):
    """Class implementing Polaris related event hooks."""

    def __init__(
        self, charm: PolarisK8sCharm, context: Context, polaris_workload: PolarisWorkload
    ) -> None:
        super().__init__(charm, "polaris")

        self.name = "polaris"
        self.state = context

        self.charm = charm
        self.context = context
        self.polaris_workload = polaris_workload

        self.polaris_manager = PolarisManager(self.charm, self.context, self.polaris_workload)
        # TODO(console): Add console manager

        self.framework.observe(self.charm.on.start, self._on_start)
        self.framework.observe(self.charm.on.config_changed, self._on_update)
        self.framework.observe(self.charm.on.update_status, self._on_update)
        self.framework.observe(self.charm.on.leader_elected, self._on_leader_elected)
        self.framework.observe(
            self.charm.on[POLARIS_CONTAINER_NAME].pebble_ready,
            self._on_update,
        )
        self.framework.observe(
            self.charm.on[PEERS_RELATION_NAME].relation_created,
            self._on_update,
        )
        self.framework.observe(
            self.charm.on[PEERS_RELATION_NAME].relation_changed,
            self._on_update,
        )

        self.framework.observe(self.charm.on.secret_changed, self._on_secret_changed)

    def _on_start(self, event: ops.StartEvent) -> None:
        """Handle the start event."""
        self.charm.unit.set_ports(REST_PORT)

    def _configured_system_user_secret_id(self) -> str | None:
        """Return configured system-user secret id, if any."""
        if not self.context.validated_config:
            return None

        return self.context.validated_config.system_user

    def _get_system_user_secret_content(self) -> dict[str, str] | None:
        """Fetch configured system-user secret content and start tracking it."""
        secret_id = self._configured_system_user_secret_id()
        if not secret_id:
            return None

        try:
            secret = self.charm.model.get_secret(id=secret_id, label=SYSTEM_USER_SECRET_LABEL)
            return secret.get_content(refresh=True)
        except (ops.ModelError, ops.SecretNotFoundError) as e:
            self.logger.error("Could not access secret %s: %s", secret_id, e)
            raise

    def _admin_password_from_secret_content(self, content: dict[str, str] | None) -> str | None:
        """Extract admin password from system-user secret content."""
        if not content:
            return None

        if not (password := content.get(ADMIN_USER)):
            self.logger.error("Password for user %s not found in secret", ADMIN_USER)
            return None

        return password

    def _validate_system_user_secret(self) -> SystemUserSecretValidation:
        """Validate the configured system-user secret and extract its password."""
        if not self._configured_system_user_secret_id():
            return SystemUserSecretValidation(configured=False)

        try:
            content = self._get_system_user_secret_content()
        except ops.SecretNotFoundError:
            return SystemUserSecretValidation(
                configured=True,
                status=CharmStatuses.SYSTEM_USER_SECRET_DOES_NOT_EXIST,
            )
        except ops.ModelError:
            return SystemUserSecretValidation(
                configured=True,
                status=CharmStatuses.SYSTEM_USER_SECRET_INSUFFICIENT_PERMISSION,
            )

        password = self._admin_password_from_secret_content(content)
        if not password:
            return SystemUserSecretValidation(
                configured=True,
                status=CharmStatuses.SYSTEM_USER_SECRET_INVALID,
            )

        return SystemUserSecretValidation(configured=True, password=password)

    def _rotate_admin_password(self, old_password: str, new_password: str) -> bool:
        """Rotate root principal credentials through Polaris management API."""
        self.charm.status.set_running_status(
            CharmStatuses.ROTATING_ROOT_PRINCIPAL_CREDENTIALS,
            scope="unit",
        )
        try:
            self.polaris_manager.reset_root_principal_credentials(old_password, new_password)
        except Exception:
            self.logger.exception("Failed to rotate Polaris root principal credentials")
            return False
        return True

    def _ensure_admin_credentials(self) -> bool:
        """Ensure leader-owned root principal credentials are set."""
        if not self.charm.unit.is_leader():
            return True

        system_user = self._validate_system_user_secret()
        if system_user.status:
            self.logger.error(system_user.status.message)
            return False

        cluster = self.context.cluster
        admin_password = (
            system_user.password or cluster.admin_password or secrets.token_hex(RANDOM_KEY_SIZE)
        )

        if cluster.admin_password == admin_password:
            return True

        if cluster.metastore_bootstrapped and not self._rotate_admin_password(
            cluster.admin_password,
            admin_password,
        ):
            return False

        cluster.set_admin_password(admin_password)
        cluster.increment_epoch()
        return True

    def _ensure_token_broker_key(self) -> None:
        """Ensure leader-owned token broker key is set."""
        if not self.charm.unit.is_leader():
            return

        cluster = self.context.cluster
        shared_key = cluster.shared_key or secrets.token_hex(RANDOM_KEY_SIZE)
        if cluster.shared_key != shared_key:
            cluster.set_shared_key(shared_key)

    def _reconcile(self, event: ops.EventBase | None = None) -> None:
        """Reconcile peer state and local workload configuration."""
        if not self.context.cluster.relation:
            self.logger.info("Peer relation not ready")
            if event:
                event.defer()
            return

        if not self.polaris_workload.ready:
            self.logger.info("Workload not ready")
            if event:
                event.defer()
            return

        if not self._ensure_admin_credentials():
            return

        self._ensure_token_broker_key()
        self.polaris_manager.update()
        # TODO(console): Update console_manager as well.

    def _on_update(self, event: ops.EventBase) -> None:
        """Handle events that may require reconciling workload configuration."""
        self._reconcile(event)

    def _on_leader_elected(self, event: ops.LeaderElectedEvent) -> None:
        """Handle the leader-elected event."""
        self.charm.unit.set_workload_version(self.polaris_workload.get_workload_version())
        self._reconcile(event)

    def _is_configured_system_user_secret(self, secret: ops.Secret) -> bool:
        """Return whether the given secret is the configured system-user secret."""
        secret_id = self._configured_system_user_secret_id()
        if not secret_id:
            return False

        if secret.label == SYSTEM_USER_SECRET_LABEL:
            return True

        short_secret_id = secret_id.removeprefix("secret:")
        return secret.id == secret_id or secret.unique_identifier == short_secret_id

    def _on_secret_changed(self, event: ops.SecretChangedEvent) -> None:
        """Handle the secret_changed event."""
        if not self.charm.unit.is_leader():
            return

        if not self._is_configured_system_user_secret(event.secret):
            return

        self.logger.info("Dealing with system-user secret update")
        try:
            content = event.secret.get_content(refresh=True)
        except (ops.ModelError, ops.SecretNotFoundError) as e:
            self.logger.error("Could not access updated secret: %s", e)
            raise

        if not self._admin_password_from_secret_content(content):
            # Status collection will surface SYSTEM_USER_SECRET_INVALID.
            return

        self._reconcile(event)

    def get_statuses(self, scope: Scope, recompute: bool = False) -> list[StatusObject]:
        """Return the list of statuses for this component."""
        # In this event handler, we specifically check for charm configuration errors
        raw_config = self.charm.config
        status_list = []
        try:
            PolarisCharmConfig.model_validate(raw_config)
        except ValidationError as ex:
            self.logger.warning(str(ex))
            missing = [str(error["loc"][0]) for error in ex.errors() if error["type"] == "missing"]
            invalid = [str(error["loc"][0]) for error in ex.errors() if error["type"] != "missing"]

            if missing:
                status_list.append(ConfigStatuses.missing_config_parameters(fields=missing))
            if invalid:
                status_list.append(ConfigStatuses.invalid_config_parameters(fields=invalid))
        else:
            if self.charm.unit.is_leader() and (
                system_user_status := self._validate_system_user_secret().status
            ):
                status_list.append(system_user_status)

        if not self.polaris_workload.ready:
            status_list.append(CharmStatuses.WAITING_PEBBLE)

        if not self.polaris_workload.active:
            status_list.append(CharmStatuses.NOT_RUNNING)

        return status_list or [CharmStatuses.ACTIVE_IDLE]
