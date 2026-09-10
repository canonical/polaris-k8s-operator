# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Ingress integration related event handlers."""

import ops
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)

from core.constants import CONSOLE_PORT, CONSOLE_TLS_PORT
from core.context import Context
from core.logging import WithLogging


class IngressEvents(ops.Object, WithLogging):
    """Class implementing Ingress integration event hooks."""

    def __init__(self, charm: ops.CharmBase, context: Context) -> None:
        super().__init__(charm, "ingress")

        self.charm = charm
        self.context = context

        self.ingress = IngressPerAppRequirer(
            self.charm,
            strip_prefix=True,
        )
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

        self.framework.observe(self.charm.on["ingress"].relation_created, self._on_update)
        self.framework.observe(self.charm.on["ingress"].relation_changed, self._on_update)

    def _on_update(self, event: ops.EventBase) -> None:
        """Handle ingress-related events that may require relation data reconciliation."""
        self.reconcile()

    def reconcile(self) -> None:
        """Publish current ingress backend requirements."""
        port = CONSOLE_TLS_PORT if self.context.console_tls.ready else CONSOLE_PORT
        scheme = "https" if port == CONSOLE_TLS_PORT else "http"

        self.ingress.provide_ingress_requirements(port=port, scheme=scheme)

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent):
        self.logger.info("This app's ingress URL: %s", event.url)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent):
        self.logger.info("This app no longer has ingress")
