# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""TLS Integration related event handlers."""

from __future__ import annotations

import ops
from charmlibs.interfaces.tls_certificates import (
    CertificateAvailableEvent,
    CertificateDeniedEvent,
    TLSCertificatesRequiresV4,
)
from data_platform_helpers.advanced_statuses.models import StatusObject
from data_platform_helpers.advanced_statuses.protocol import ManagerStatusProtocol
from data_platform_helpers.advanced_statuses.types import Scope

from core.constants import (
    CONSOLE_CONTAINER_NAME,
    CONSOLE_PORT,
    CONSOLE_TLS_PORT,
    TLS_RELATION_NAME,
)
from core.context import Context
from core.logging import WithLogging
from core.workload.console import ConsoleWorkload
from managers.console import ConsoleManager
from managers.tls import TLSManager
from protocols import CharmWithReconcile


class _TLSStatuses:
    """Status objects related to the TLS integration."""

    TLS_CERTIFICATE_NOT_READY = StatusObject(
        status="waiting",
        message="Waiting for TLS certificate",
    )


TLSStatuses = _TLSStatuses()


class TLSEvents(ops.Object, WithLogging, ManagerStatusProtocol):
    """Class implementing TLS Integration event hooks."""

    def __init__(
        self, charm: CharmWithReconcile, context: Context, console_workload: ConsoleWorkload
    ) -> None:
        super().__init__(charm, "tls")

        self.name = "tls"
        self.state = context

        self.charm = charm
        self.context = context
        self.console_workload = console_workload
        self.console_manager = ConsoleManager(self.context, self.console_workload)
        self.tls_manager = TLSManager(context, charm.polaris_workload)  # type: ignore[attr-defined]

        self.certificates = TLSCertificatesRequiresV4(
            charm=self.charm,
            relationship_name=TLS_RELATION_NAME,
            certificate_requests=[self.tls_manager.build_console_certificate_request()],
        )
        self.context._tls_certificates_requirer = self.certificates

        self.framework.observe(self.certificates.on.certificate_available, self._on_certificate)
        self.framework.observe(
            self.certificates.on.certificate_denied, self._on_certificate_denied
        )
        self.framework.observe(self.charm.on[TLS_RELATION_NAME].relation_created, self._on_update)
        self.framework.observe(
            self.charm.on[TLS_RELATION_NAME].relation_broken,
            self._on_relation_broken,
        )
        self.framework.observe(
            self.charm.on[CONSOLE_CONTAINER_NAME].pebble_ready,
            self._on_update,
        )

    def _has_assigned_certificate(self) -> bool:
        """Return whether the TLS library has an assigned certificate for this unit."""
        certificates, _ = self.certificates.get_assigned_certificates()
        return bool(certificates)

    def _on_update(self, event: ops.EventBase) -> None:
        """Handle TLS events that may require state reconciliation."""
        self.reconcile(event)

    def _on_certificate(self, event: CertificateAvailableEvent) -> None:
        """Handle the certificate_available event from the TLS provider."""
        self.reconcile(event)

    def _on_certificate_denied(self, event: CertificateDeniedEvent) -> None:
        """Handle the certificate_denied event from the TLS provider."""
        self.logger.error(event.error.message)

    def _on_relation_broken(self, event: ops.RelationBrokenEvent) -> None:
        """Handle the client-certificates relation-broken event."""
        if not self.context.cluster.relation:
            self.logger.info("Peer relation not ready")
            event.defer()
            return

        if not self.console_workload.ready:
            self.logger.info("Console workload not ready")
            event.defer()
            return

        self.reconcile(event)

    def reconcile(self, event: ops.EventBase | None = None) -> None:
        """Reconcile TLS relation data and current console exposure mode."""
        if not self.context.cluster.relation:
            self.logger.info("Peer relation not ready")
            if event:
                event.defer()
            return

        if not self.console_workload.ready:
            self.logger.info("Console workload not ready")
            if event:
                event.defer()
            return

        self.console_manager.update()
        console_tls = self.context.console_tls
        port = CONSOLE_TLS_PORT if console_tls.ready else CONSOLE_PORT
        self.charm.unit.set_ports(port)

        self.charm.reconcile("ingress_events")

    def get_statuses(self, scope: Scope, recompute: bool = False) -> list[StatusObject]:
        """Return the list of statuses for this component."""
        if not self.context.tls_relation:
            return []

        if not self._has_assigned_certificate():
            return [TLSStatuses.TLS_CERTIFICATE_NOT_READY]

        return []
