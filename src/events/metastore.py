# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Metastore relation event handlers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import ops
from charms.data_platform_libs.v0.data_interfaces import (
    STATUS_FIELD,
    DatabaseRequires,
    RelationStatus,
    StatusRaisedEvent,
    StatusResolvedEvent,
)
from data_platform_helpers.advanced_statuses.models import StatusObject
from data_platform_helpers.advanced_statuses.protocol import ManagerStatusProtocol
from data_platform_helpers.advanced_statuses.types import Scope

from core.constants import METASTORE_RELATION_NAME, POLARIS_METASTORE_DATABASE_NAME
from core.context import Context
from core.logging import WithLogging
from core.statuses import MetastoreStatuses
from core.workload.polaris import PolarisWorkload
from events import BaseEventHandler
from managers.polaris import PolarisManager

if TYPE_CHECKING:
    from charm import PolarisK8sCharm


class MetastoreEvents(BaseEventHandler, WithLogging, ManagerStatusProtocol):
    """Class implementing metastore relation hooks."""

    def __init__(
        self, charm: PolarisK8sCharm, context: Context, polaris_workload: PolarisWorkload
    ) -> None:
        super().__init__(charm, "metastore")

        self.name = "metastore"
        self.state = context

        self.charm = charm
        self.context = context
        self.polaris_workload = polaris_workload

        self.polaris_manager = PolarisManager(self.charm, self.context, self.polaris_workload)
        self.metastore = DatabaseRequires(
            charm=self.charm,
            relation_name=METASTORE_RELATION_NAME,
            database_name=POLARIS_METASTORE_DATABASE_NAME,
            extra_user_roles="SUPERUSER",
        )

        self.framework.observe(self.metastore.on.database_created, self._on_update)
        self.framework.observe(self.metastore.on.endpoints_changed, self._on_update)
        self.framework.observe(self.metastore.on.status_raised, self._on_status_update)
        self.framework.observe(self.metastore.on.status_resolved, self._on_status_update)
        self.framework.observe(
            self.charm.on[METASTORE_RELATION_NAME].relation_broken,
            self._on_relation_broken,
        )

    def _reconcile(self, event: ops.EventBase | None = None) -> None:
        """Reconcile metastore relation data and workload configuration."""
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

        if not self.context.metastore.ready:
            self.logger.info("Metastore relation not ready")
            return

        self.polaris_manager.update()

    def _on_update(self, event: ops.EventBase) -> None:
        """Handle metastore relation events."""
        self._reconcile(event)

    def _on_status_update(self, event: StatusRaisedEvent | StatusResolvedEvent) -> None:
        """Handle provider-side metastore status changes."""
        self._reconcile(event)

    def _on_relation_broken(self, event: ops.RelationBrokenEvent) -> None:
        """Handle the metastore relation-broken event."""
        if self.charm.unit.is_leader():
            self.context.cluster.set_metastore_bootstrapped(False)

        if self.polaris_workload.ready:
            self.polaris_workload.stop()

    def _provider_statuses(self) -> list[RelationStatus]:
        """Return provider-side statuses from the metastore relation."""
        relation = self.context.metastore_relation
        if not relation or not relation.app:
            return []

        raw_statuses = relation.data[relation.app].get(STATUS_FIELD, "[]")
        return [RelationStatus(**status) for status in json.loads(raw_statuses)]

    def get_statuses(self, scope: Scope, recompute: bool = False) -> list[StatusObject]:
        """Return the list of statuses for this component."""
        status_list = []

        if not self.context.metastore_relation:
            return [MetastoreStatuses.METASTORE_RELATION_MISSING]

        for status in self._provider_statuses():
            if status.is_fatal:
                status_list.append(
                    MetastoreStatuses.provider_error(
                        message=status.message,
                        resolution=status.resolution,
                    )
                )

        if not self.context.metastore.ready:
            status_list.append(MetastoreStatuses.METASTORE_NOT_READY)

        return status_list
