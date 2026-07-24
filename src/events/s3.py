# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""S3 Integration related event handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import ops
from data_platform_helpers.advanced_statuses.models import StatusObject
from data_platform_helpers.advanced_statuses.protocol import ManagerStatusProtocol
from data_platform_helpers.advanced_statuses.types import Scope
from object_storage import (
    S3Requirer,
    StorageConnectionInfoChangedEvent,
    StorageConnectionInfoGoneEvent,
)

from core.constants import S3_RELATION_NAME
from core.logging import WithLogging
from events import BaseEventHandler
from managers.polaris import PolarisManager
from managers.tls import TLSManager

if TYPE_CHECKING:
    from charm import PolarisK8sCharm


class _ObjectStorageStatuses:
    """Status objects related to the object storage integration."""

    OBJECT_STORAGE_RELATION_MISSING = StatusObject(
        status="blocked",
        message="Missing mandatory object storage relation",
        action="Relate the charm to an object storage integrator",
    )
    OBJECT_STORAGE_NOT_READY = StatusObject(
        status="waiting",
        message="Waiting for object storage relation data",
    )
    IMPORTING_OBJECT_STORAGE_CA = StatusObject(
        status="maintenance",
        message="Importing object storage CA certificate",
        running="blocking",
    )

    @staticmethod
    def missing_parameters(fields: list[str]) -> StatusObject:
        """Return a status for missing object storage relation data."""
        fields_str = ", ".join(f"'{field}'" for field in fields)
        return StatusObject(
            status="waiting",
            message=f"Missing object storage parameter(s): {fields_str}",
            action=f"Set object storage parameter(s): {fields_str}",
        )


ObjectStorageStatuses = _ObjectStorageStatuses()


class S3Events(BaseEventHandler, WithLogging, ManagerStatusProtocol):
    """Class implementing S3 Integration event hooks."""

    def __init__(self, charm: PolarisK8sCharm) -> None:
        super().__init__(charm, "s3")

        self.name = "s3"
        self.state = charm.context

        self.charm = charm
        self.context = charm.context
        self.workload = charm.polaris_workload

        self.s3_requirer = S3Requirer(self.charm, S3_RELATION_NAME)
        self.context._s3_requirer = self.s3_requirer
        self.polaris_manager = PolarisManager(self.charm, self.context, self.workload)
        self.tls_manager = TLSManager(self.context, self.workload)

        self.framework.observe(
            self.s3_requirer.on.storage_connection_info_changed, self._on_s3_credential_changed
        )
        self.framework.observe(
            self.s3_requirer.on.storage_connection_info_gone, self._on_s3_credential_gone
        )

    def _reconcile(self, event: ops.EventBase | None = None) -> None:
        """Reconcile S3 relation data and workload configuration."""
        if not self.context.cluster.relation:
            self.logger.info("Peer relation not ready")
            if event:
                event.defer()
            return

        if not self.workload.ready:
            self.logger.info("Workload not ready")
            if event:
                event.defer()
            return

        if not self.context.s3.ready:
            self.logger.info("Object storage relation not ready")
            return

        force_restart = False
        if self.context.s3.has_custom_ca:
            self.charm.status.set_running_status(
                ObjectStorageStatuses.IMPORTING_OBJECT_STORAGE_CA,
                scope="unit",
            )
            force_restart = self.tls_manager.import_ca_chain(self.context.s3.tls_ca_chain)
        else:
            force_restart = self.tls_manager.reset()

        self.polaris_manager.update(force_restart=force_restart)

    def _on_s3_credential_changed(self, event: StorageConnectionInfoChangedEvent) -> None:
        """Handle the `StorageConnectionInfoChangedEvent` event from S3 integrator."""
        self._reconcile(event)

    def _on_s3_credential_gone(self, event: StorageConnectionInfoGoneEvent) -> None:
        """Handle the `StorageConnectionInfoGoneEvent` event for S3 integrator."""
        self.tls_manager.reset()
        self._reconcile(event)

    def get_statuses(self, scope: Scope, recompute: bool = False) -> list[StatusObject]:
        """Return the list of statuses for this component."""
        if not self.context.s3_relation:
            return [ObjectStorageStatuses.OBJECT_STORAGE_RELATION_MISSING]

        # TODO(object-storage): Add a blocking status if we have multiple types of object
        # storages.

        if missing_fields := self.context.s3.missing_fields:
            return [ObjectStorageStatuses.missing_parameters(fields=missing_fields)]

        if not self.context.s3.ready:
            return [ObjectStorageStatuses.OBJECT_STORAGE_NOT_READY]

        return []
