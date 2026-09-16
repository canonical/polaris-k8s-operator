# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm Context definition and parsing logic."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import ops
from data_platform_helpers.advanced_statuses.components import StatusesState
from data_platform_helpers.advanced_statuses.protocol import StatusesStateProtocol
from dpcharmlibs.interfaces import (
    OpsOtherPeerUnitRepositoryInterface,
    OpsPeerRepositoryInterface,
    OpsPeerUnitRepositoryInterface,
)
from pydantic import ValidationError

from config.charm import PolarisCharmConfig
from core.constants import (
    METASTORE_RELATION_NAME,
    OAUTH_CA_RELATION_NAME,
    OAUTH_RELATION_NAME,
    PEERS_RELATION_NAME,
    S3_RELATION_NAME,
    STATUS_RELATION_NAME,
    TLS_RELATION_NAME,
)
from core.logging import WithLogging
from core.models import (
    ConsoleTLS,
    Metastore,
    OAuth,
    PeerAppModel,
    PeerUnitModel,
    PolarisCluster,
    PolarisServer,
    S3Storage,
)

if TYPE_CHECKING:
    from charmlibs.interfaces.certificate_transfer import CertificateTransferRequires
    from charmlibs.interfaces.tls_certificates import TLSCertificatesRequiresV4
    from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
    from object_storage import S3Requirer


class Context(ops.Object, WithLogging, StatusesStateProtocol):
    """Properties and relations of the charm."""

    # These elements are injected by integration event handlers to avoid duplicated side-effects
    _s3_requirer: S3Requirer
    _tls_certificates_requirer: TLSCertificatesRequiresV4
    _ingress_requirer: IngressPerAppRequirer
    _oauth_ca_requirer: CertificateTransferRequires

    def __init__(self, charm: ops.CharmBase) -> None:
        super().__init__(charm, "charm_context")
        self.charm = charm
        self.raw_config = charm.config
        self.statuses = StatusesState(self, STATUS_RELATION_NAME)
        self.peer_app_interface = OpsPeerRepositoryInterface(
            model=charm.model, relation_name=PEERS_RELATION_NAME, data_model=PeerAppModel
        )
        self.peer_unit_interface = OpsPeerUnitRepositoryInterface(
            model=charm.model, relation_name=PEERS_RELATION_NAME, data_model=PeerUnitModel
        )

    @cached_property
    def validated_config(self) -> PolarisCharmConfig | None:
        """Charm validated configuration.

        None if the charm configuration could not be validated.
        """
        try:
            return PolarisCharmConfig.model_validate(self.raw_config)
        except ValidationError:
            return None

    def get_secret_from_id(self, secret_id: str) -> dict[str, str]:
        """Resolve a Juju secret id and return its content."""
        try:
            secret_content = self.charm.model.get_secret(id=secret_id).get_content(refresh=True)
        except ops.SecretNotFoundError:
            raise ops.SecretNotFoundError(f"The secret '{secret_id}' does not exist.")
        except ops.ModelError:
            raise

        return secret_content

    @property
    def peer_relation(self) -> ops.model.Relation | None:
        """Get the Polaris peer relation."""
        return self.model.get_relation(PEERS_RELATION_NAME)

    @property
    def peer_units_data_interfaces(
        self,
    ) -> dict[ops.model.Unit, OpsOtherPeerUnitRepositoryInterface[PeerUnitModel]]:
        """Get unit data interface of all peer units from the Polaris peer relation."""
        if not self.peer_relation or not self.peer_relation.units:
            return {}

        return {
            unit: OpsOtherPeerUnitRepositoryInterface(
                model=self.charm.model,
                relation_name=PEERS_RELATION_NAME,
                unit=unit,
                data_model=PeerUnitModel,
            )
            for unit in self.peer_relation.units
        }

    @property
    def unit_server(self) -> PolarisServer:
        """Get the server state of this unit."""
        return PolarisServer(
            relation=self.peer_relation,
            data_interface=self.peer_unit_interface,
            component=self.model.unit,
        )

    @property
    def cluster(self) -> PolarisCluster:
        """Get the cluster state of the entire Polaris deployment."""
        return PolarisCluster(
            relation=self.peer_relation,
            data_interface=self.peer_app_interface,
            component=self.model.app,
        )

    @property
    def ingress_relation(self) -> ops.model.Relation | None:
        """Get the ingress relation."""
        return self.model.get_relation("ingress")

    @property
    def ingress_url(self) -> str:
        """Get the externally reachable ingress URL, if known."""
        if not hasattr(self, "_ingress_requirer"):
            return ""
        return self._ingress_requirer.url or ""

    @property
    def metastore_relation(self) -> ops.model.Relation | None:
        """Get the metastore relation."""
        return self.model.get_relation(METASTORE_RELATION_NAME)

    @property
    def metastore(self) -> Metastore:
        """Get the metastore relation state."""
        return Metastore(relation=self.metastore_relation, model=self.charm.model)

    @property
    def oauth(self) -> OAuth:
        """Get the oauth relation state."""
        return OAuth(relation=self.oauth_relation, model=self.charm.model)

    @property
    def oauth_relation(self) -> ops.model.Relation | None:
        """Get the oauth relation."""
        return self.model.get_relation(OAUTH_RELATION_NAME)

    @property
    def oauth_ca_relation(self) -> ops.model.Relation | None:
        """Get the oauth-ca relation."""
        return self.model.get_relation(OAUTH_CA_RELATION_NAME)

    @property
    def oauth_ca_certificates(self) -> set[str]:
        """Get certificates transferred on the oauth-ca relation."""
        if not hasattr(self, "_oauth_ca_requirer") or not self.oauth_ca_relation:
            return set()
        return self._oauth_ca_requirer.get_all_certificates(self.oauth_ca_relation.id)

    @property
    def s3_relation(self) -> ops.model.Relation | None:
        """Get the s3 relation."""
        return self.model.get_relation(S3_RELATION_NAME)

    @property
    def s3(self) -> S3Storage:
        """Get the s3 relation state."""
        if not hasattr(self, "_s3_requirer"):
            return S3Storage({})
        return S3Storage(self._s3_requirer.get_storage_connection_info(self.s3_relation))

    @property
    def tls_relation(self) -> ops.model.Relation | None:
        """Get the TLS relation."""
        return self.model.get_relation(TLS_RELATION_NAME)

    @property
    def console_tls(self) -> ConsoleTLS:
        """Get the console TLS integration state."""
        return ConsoleTLS(
            relation=self.tls_relation,
            certificates_requirer=getattr(self, "_tls_certificates_requirer", None),
        )
