# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""OAuth Integration related event handlers."""

from __future__ import annotations

import ops
from charmlibs.interfaces.certificate_transfer import CertificateTransferRequires
from charmlibs.interfaces.oauth import ClientConfig, OAuthRequirer
from data_platform_helpers.advanced_statuses.models import StatusObject
from data_platform_helpers.advanced_statuses.protocol import ManagerStatusProtocol
from data_platform_helpers.advanced_statuses.types import Scope

from core.constants import (
    OAUTH_CA_RELATION_NAME,
    OAUTH_CA_CERTIFICATE,
    OAUTH_CALLBACK_PATH,
    OAUTH_RELATION_NAME,
)
from core.context import Context
from core.logging import WithLogging
from core.workload.console import ConsoleWorkload
from core.workload.polaris import PolarisWorkload
from managers.console import ConsoleManager
from managers.polaris import PolarisManager
from managers.tls import TLSManager


class _OAuthStatuses:
    """Status objects related to the OAuth integration."""

    OAUTH_REQUIRES_INGRESS = StatusObject(
        status="blocked",
        message="OAuth integration requires ingress",
        action="Relate the charm to ingress before using OAuth",
    )
    OAUTH_WAITING_FOR_INGRESS_URL = StatusObject(
        status="waiting",
        message="Waiting for ingress URL required by OAuth",
    )
    OAUTH_REQUIRES_HTTPS_INGRESS = StatusObject(
        status="blocked",
        message="OAuth integration requires an HTTPS ingress URL",
        action="Enable TLS for the Console ingress before using OAuth",
    )
    OAUTH_PROVIDER_NOT_READY = StatusObject(
        status="waiting",
        message="Waiting for OAuth provider metadata and client credentials",
    )


OAuthStatuses = _OAuthStatuses()

OAUTH_GRANT_TYPES = ["authorization_code", "client_credentials"]
OAUTH_SCOPES = "openid profile email"
OAUTH_CLIENT_AUTHN_METHOD = "client_secret_post"


class OAuthEvents(ops.Object, WithLogging, ManagerStatusProtocol):
    """Class implementing OAuth Integration event hooks."""

    def __init__(
        self,
        charm: ops.CharmBase,
        context: Context,
        polaris_workload: PolarisWorkload,
        console_workload: ConsoleWorkload,
    ) -> None:
        super().__init__(charm, "oauth")

        self.name = "oauth"
        self.state = context

        self.charm = charm
        self.context = context
        self.polaris_workload = polaris_workload
        self.console_workload = console_workload

        client_config = None
        self.oauth = OAuthRequirer(self.charm, client_config, relation_name=OAUTH_RELATION_NAME)
        self.cert_transfer = CertificateTransferRequires(self.charm, OAUTH_CA_RELATION_NAME)
        self.context._oauth_ca_requirer = self.cert_transfer
        self.polaris_manager = PolarisManager(
            self.context, self.polaris_workload, is_leader=self.charm.unit.is_leader()
        )
        self.console_manager = ConsoleManager(self.context, self.console_workload)
        self.tls_manager = TLSManager(self.context, self.polaris_workload)

        self.framework.observe(
            self.charm.on[OAUTH_RELATION_NAME].relation_created, self._on_update
        )
        self.framework.observe(self.oauth.on.oauth_info_changed, self._on_update)
        self.framework.observe(self.oauth.on.oauth_info_removed, self._on_update)
        self.framework.observe(self.oauth.on.invalid_client_config, self._on_update)
        self.framework.observe(self.cert_transfer.on.certificate_set_updated, self._on_update)
        self.framework.observe(self.cert_transfer.on.certificates_removed, self._on_update)

    def _on_update(self, event: ops.EventBase) -> None:
        """Handle oauth-related events that may require reconciliation."""
        self.reconcile(event)

    def oauth_client_config(self) -> ClientConfig | None:
        """Build the oauth client configuration published to the provider."""
        if not self.context.ingress_url or not self.context.ingress_url.startswith("https://"):
            return None

        return ClientConfig(
            redirect_uri=f"{self.context.ingress_url}{OAUTH_CALLBACK_PATH}",
            scope=OAUTH_SCOPES,
            grant_types=OAUTH_GRANT_TYPES,
            audience=[],
            token_endpoint_auth_method=OAUTH_CLIENT_AUTHN_METHOD,
        )

    def reconcile(self, event: ops.EventBase | None = None) -> None:
        """Reconcile OAuth relations and workload readiness prerequisites."""
        if not self.context.oauth_relation:
            return

        if not self.context.cluster.relation:
            self.logger.info("Peer relation not ready")
            if event:
                event.defer()
            return

        if not self.polaris_workload.active or not self.console_workload.ready:
            # We need an active polaris so that we can create the oidc user
            self.logger.info("Workloads not ready")
            if event:
                event.defer()
            return

        self.polaris_manager.ensure_oidc_principal_role()

        if client_config := self.oauth_client_config():
            self.oauth.update_client_config(client_config)

        force_restart = self.tls_manager.ensure_certificates_imported(
            sorted(self.context.oauth_ca_certificates),
            "oauth-ca",
            OAUTH_CA_CERTIFICATE,
        )
        self.console_manager.update()
        self.polaris_manager.update(force_restart=force_restart)

    def get_statuses(self, scope: Scope, recompute: bool = False) -> list[StatusObject]:
        """Return the list of statuses for this component."""
        if not self.context.oauth_relation:
            return []

        if not self.context.ingress_relation:
            return [OAuthStatuses.OAUTH_REQUIRES_INGRESS]

        if not self.context.ingress_url:
            return [OAuthStatuses.OAUTH_WAITING_FOR_INGRESS_URL]

        if not self.context.ingress_url.startswith("https://"):
            return [OAuthStatuses.OAUTH_REQUIRES_HTTPS_INGRESS]

        if not self.context.oauth.ready:
            return [OAuthStatuses.OAUTH_PROVIDER_NOT_READY]

        return []
