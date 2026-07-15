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


class Metastore:
    """State collection for the metastore relation."""

    def __init__(self, relation: ops.model.Relation | None, model: ops.model.Model) -> None:
        self.relation = relation
        self.model = model

    @property
    def _relation_data(self) -> Mapping[str, str]:
        """Return the metastore provider relation data."""
        if not self.relation or not self.relation.app:
            return {}
        return self.relation.data[self.relation.app]

    @property
    def _user_secret_content(self) -> dict[str, str]:
        """Return the metastore user secret content."""
        if not (secret_id := self._relation_data.get("secret-user")):
            return {}

        try:
            return self.model.get_secret(id=secret_id).get_content(refresh=True)
        except (ops.ModelError, ops.SecretNotFoundError):
            logger.warning("Could not access metastore user secret")
            return {}

    @property
    def resource(self) -> str:
        """Return the metastore database name."""
        return self._relation_data.get("database") or POLARIS_METASTORE_DATABASE_NAME

    @property
    def endpoints(self) -> str:
        """Return the metastore endpoints."""
        return self._relation_data.get("endpoints") or ""

    @property
    def endpoint(self) -> str:
        """Return the first metastore endpoint."""
        return self.endpoints.split(",")[0]

    @property
    def username(self) -> str:
        """Return the metastore username."""
        return (
            self._user_secret_content.get("username") or self._relation_data.get("username") or ""
        )

    @property
    def password(self) -> str:
        """Return the metastore password."""
        return (
            self._user_secret_content.get("password") or self._relation_data.get("password") or ""
        )

    @property
    def jdbc_url(self) -> str:
        """Return the JDBC URL for the metastore."""
        if not self.endpoint or not self.resource:
            return ""
        return f"jdbc:postgresql://{self.endpoint}/{self.resource}"

    @property
    def ready(self) -> bool:
        """Return whether the metastore relation has complete connection data."""
        return bool(self.endpoint and self.username and self.password and self.resource)


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
