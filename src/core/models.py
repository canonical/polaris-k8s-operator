# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collection of state objects for the Polaris relations, apps and units."""

import logging
from collections.abc import Mapping
from typing import Annotated, Any, final

import ops
from dpcharmlibs.interfaces import (
    OpsOtherPeerUnitRepositoryInterface,
    OpsPeerRepositoryInterface,
    OpsPeerUnitRepositoryInterface,
    OptionalSecretStr,
    PeerModel,
)
from pydantic import Field

from core.constants import (
    ADMIN_USER,
    POLARIS_METASTORE_DATABASE_NAME,
    SYSTEM_USER_SECRET_LABEL_SUFFIX,
)

REQUIRED_S3_PARAMETERS = ["access-key", "secret-key", "bucket", "endpoint", "region"]

logger = logging.getLogger(__name__)


InternalUserSecret = Annotated[
    OptionalSecretStr, Field(exclude=True, default=None), SYSTEM_USER_SECRET_LABEL_SUFFIX
]


class PeerAppModel(PeerModel):
    """Model for the peer application data."""

    charmed_operator_password: InternalUserSecret = Field(default="")
    shared_key: str = Field(default="")
    metastore_bootstrapped: bool = Field(default=False)
    epoch: int = Field(default=1)


class PeerUnitModel(PeerModel):
    """Model for the peer unit data."""

    truststore_password: str = Field(default="")


class RelationState:
    """Relation state object."""

    def __init__(
        self,
        relation: ops.model.Relation | None,
        data_interface: OpsPeerRepositoryInterface[PeerAppModel]
        | OpsPeerUnitRepositoryInterface[PeerUnitModel]
        | OpsOtherPeerUnitRepositoryInterface[PeerUnitModel],
        component: ops.model.Unit | ops.model.Application | None,
    ) -> None:
        self.relation = relation
        self.data_interface = data_interface
        self.component = component
        self.model = self.data_interface.build_model(self.relation.id) if self.relation else None

    def update(self, items: dict[str, Any]) -> None:
        """Write to relation data."""
        # `self.model` is only built when `self.relation` exists, so both are checked together.
        if not self.relation or self.model is None:
            logger.warning(
                "Fields %s were attempted to be written on the relation before it exists.",
                list(items.keys()),
            )
            return

        delete_fields = [key for key in items if not items[key]]
        update_content = {k: items[k] for k in items if k not in delete_fields}

        for field, value in update_content.items():
            setattr(self.model, field.replace("-", "_"), value)

        for field in delete_fields:
            setattr(self.model, field.replace("-", "_"), None)

        self.data_interface.write_model(self.relation.id, self.model)


class S3Storage:
    """State collection for the S3-compatible object storage relation."""

    def __init__(self, info: Mapping[str, Any]) -> None:
        self.info = info

    @property
    def missing_fields(self) -> list[str]:
        """Return missing required object storage fields."""
        return [field for field in REQUIRED_S3_PARAMETERS if not self.info.get(field)]

    @property
    def ready(self) -> bool:
        """Return whether the object storage relation has complete connection data."""
        return not self.missing_fields

    @property
    def access_key(self) -> str:
        """Return the object storage access key."""
        return str(self.info.get("access-key") or "")

    @property
    def secret_key(self) -> str:
        """Return the object storage secret key."""
        return str(self.info.get("secret-key") or "")

    @property
    def bucket(self) -> str:
        """Return the object storage bucket."""
        return str(self.info.get("bucket") or "")

    @property
    def endpoint(self) -> str:
        """Return the object storage endpoint."""
        return str(self.info.get("endpoint") or "")

    @property
    def region(self) -> str:
        """Return the object storage region."""
        return str(self.info.get("region") or "")

    @property
    def path(self) -> str:
        """Return the object storage path."""
        return str(self.info.get("path") or "")

    @property
    def uri_style(self) -> str:
        """Return the object storage URI style."""
        return str(self.info.get("s3-uri-style") or "")

    @property
    def tls_ca_chain(self) -> list[str]:
        """Return the object storage TLS CA chain."""
        ca_chain: Any = self.info.get("tls-ca-chain") or []
        if isinstance(ca_chain, str):
            return [ca_chain]
        return list(ca_chain)

    @property
    def has_custom_ca(self) -> bool:
        """Return whether object storage provides a custom CA chain."""
        return bool(self.tls_ca_chain)


class Metastore:
    """State collection for the metastore relation."""

    def __init__(self, relation: ops.model.Relation | None, model: ops.model.Model) -> None:
        self._relation = relation
        self._model = model

    @property
    def relation_data(self) -> Mapping[str, str]:
        """Return the metastore provider relation data."""
        if not self._relation or not self._relation.app:
            return {}
        return self._relation.data[self._relation.app]

    def _user_secret_content(self) -> dict[str, str]:
        """Return the metastore user secret content."""
        if not (secret_id := self.relation_data.get("secret-user")):
            return {}

        try:
            return self._model.get_secret(id=secret_id).get_content(refresh=True)
        except (ops.ModelError, ops.SecretNotFoundError):
            logger.warning("Could not access metastore user secret")
            return {}

    @property
    def database(self) -> str:
        """Return the metastore database name."""
        return self.relation_data.get("database") or POLARIS_METASTORE_DATABASE_NAME

    @property
    def endpoint(self) -> str:
        """Return the first metastore endpoint."""
        endpoints = self.relation_data.get("endpoints") or ""
        return endpoints.split(",")[0]

    @property
    def username(self) -> str:
        """Return the metastore username."""
        return (
            self._user_secret_content().get("username") or self.relation_data.get("username") or ""
        )

    @property
    def password(self) -> str:
        """Return the metastore password."""
        return (
            self._user_secret_content().get("password") or self.relation_data.get("password") or ""
        )

    @property
    def jdbc_url(self) -> str:
        """Return the JDBC URL for the metastore."""
        if not self.endpoint or not self.database:
            return ""
        return f"jdbc:postgresql://{self.endpoint}/{self.database}"

    @property
    def ready(self) -> bool:
        """Return whether the metastore relation has complete connection data."""
        return bool(self.endpoint and self.username and self.password and self.database)


@final
class PolarisServer(RelationState):
    """State/Relation data collection for a unit."""

    model: PeerUnitModel

    def __init__(
        self,
        relation: ops.model.Relation | None,
        data_interface: OpsPeerUnitRepositoryInterface[PeerUnitModel]
        | OpsOtherPeerUnitRepositoryInterface[PeerUnitModel],
        component: ops.model.Unit,
    ) -> None:
        super().__init__(relation, data_interface, component)
        self.data_interface = data_interface
        self.unit = component

    @property
    def unit_id(self) -> int:
        """The id of the unit from the unit name."""
        return int(self.unit.name.split("/")[1])

    @property
    def unit_name(self) -> str:
        """The unit's name."""
        return self.unit.name

    @property
    def truststore_password(self) -> str:
        """Retrieve the unit truststore password."""
        if not self.model:
            return ""
        return self.model.truststore_password or ""

    def set_truststore_password(self, password: str) -> None:
        """Update the unit truststore password in peer unit databag."""
        self.update({"truststore_password": password})


@final
class PolarisCluster(RelationState):
    """State/Relation data collection for the Polaris application."""

    model: PeerAppModel

    def __init__(
        self,
        relation: ops.model.Relation | None,
        data_interface: OpsPeerRepositoryInterface[PeerAppModel],
        component: ops.model.Application,
    ) -> None:
        super().__init__(relation, data_interface, component)
        self.app = component
        self.data_interface = data_interface

    @property
    def admin_password(self) -> str:
        """Retrieve the password for the Polaris admin user."""
        if not self.model:
            return ""
        return self.model.charmed_operator_password or ""

    def set_admin_password(self, password: str) -> None:
        """Update the admin password in peer app databag with given content."""
        self.update({f"{ADMIN_USER}_password": password})

    @property
    def shared_key(self) -> str:
        """Retrieve the shared token broker key."""
        if not self.model:
            return ""
        return self.model.shared_key or ""

    def set_shared_key(self, key: str) -> None:
        """Update the shared token broker key in peer app databag with given content."""
        self.update({"shared_key": key})

    @property
    def ready(self) -> bool:
        """Do we have everything we need to start the cluster?"""
        return bool(self.admin_password) and bool(self.shared_key)

    @property
    def epoch(self) -> int:
        """Cluster state epoch."""
        if not self.model:
            return -1
        return self.model.epoch or -1

    @property
    def metastore_bootstrapped(self) -> bool:
        """Return whether the metastore has been bootstrapped."""
        if not self.model:
            return False
        return self.model.metastore_bootstrapped

    def set_metastore_bootstrapped(self, bootstrapped: bool) -> None:
        """Update the metastore bootstrap state in peer app databag."""
        self.update({"metastore_bootstrapped": bootstrapped})

    def increment_epoch(self) -> None:
        """Increment cluster state epoch."""
        self.update({"epoch": max(self.epoch + 1, 1)})
