# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Certificates transfer Integration related event handlers."""

from __future__ import annotations

import ops
from charmlibs.interfaces.certificate_transfer import CertificateTransferRequires

from core.constants import (
    ADDITIONAL_CA_CERTIFICATE,
    POLARIS_CONTAINER_NAME,
    RECEIVE_CERTS_RELATION_NAME,
)
from core.context import Context
from core.logging import WithLogging
from core.workload.polaris import PolarisWorkload
from managers.polaris import PolarisManager
from managers.tls import TLSManager


class CertificatesTransferEvents(ops.Object, WithLogging):
    """Class implementing certificates transfer Integration event hooks."""

    def __init__(
        self,
        charm: ops.CharmBase,
        context: Context,
        polaris_workload: PolarisWorkload,
    ) -> None:
        super().__init__(charm, "certs")

        self.name = ""
        self.state = context

        self.charm = charm
        self.context = context
        self.polaris_workload = polaris_workload

        self.cert_transfer = CertificateTransferRequires(self.charm, RECEIVE_CERTS_RELATION_NAME)
        self.polaris_manager = PolarisManager(
            self.context, self.polaris_workload, is_leader=self.charm.unit.is_leader()
        )
        self.tls_manager = TLSManager(self.context, self.polaris_workload)

        self.context._additional_ca_requirer = self.cert_transfer
        self.framework.observe(self.cert_transfer.on.certificate_set_updated, self._on_update)
        self.framework.observe(self.cert_transfer.on.certificates_removed, self._on_update)
        self.framework.observe(
            self.charm.on[POLARIS_CONTAINER_NAME].pebble_ready,
            self._on_update,
        )

    def _on_update(self, event: ops.EventBase) -> None:
        """Handle oauth-related events that may require reconciliation."""
        self.reconcile(event)

    def reconcile(self, event: ops.EventBase | None = None) -> None:
        """Reconcile OAuth relations and workload readiness prerequisites."""
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

        force_restart = self.tls_manager.ensure_certificates_imported(
            sorted(self.context.additional_ca_certificates),
            "additional-ca",
            ADDITIONAL_CA_CERTIFICATE,
        )
        self.polaris_manager.update(force_restart=force_restart)
