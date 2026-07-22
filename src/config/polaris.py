# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Polaris workload configuration."""

from core.constants import ADMIN_USER, REALM, SYMMETRIC_KEY
from core.context import Context
from core.logging import WithLogging


class PolarisConfig(WithLogging):
    """Polaris configuration."""

    def __init__(self, context: Context) -> None:
        self.context = context

    @property
    def bootstrap_credentials(self) -> str:
        """Return Polaris root principal credentials."""
        return f"{REALM},{ADMIN_USER},{self.context.cluster.admin_password}"

    @property
    def _base_conf(self) -> dict[str, str]:
        """Return base Polaris configurations."""
        conf = {
            "polaris.bootstrap.credentials": self.bootstrap_credentials,
            "polaris.readiness.ignore-severe-issues": "true",
            "polaris.realm-context.realms": "POLARIS",
            "polaris.realm-context.require-header": "true",
            "polaris.authentication.token-broker.type": "symmetric-key",
            "polaris.authentication.token-broker.symmetric-key.file": SYMMETRIC_KEY,
        }

        metastore = self.context.metastore
        if metastore.ready:
            conf.update(
                {
                    "polaris.persistence.type": "relational-jdbc",
                    "quarkus.datasource.db-kind": "postgresql",
                    "quarkus.datasource.jdbc.url": metastore.jdbc_url,
                    "quarkus.datasource.username": metastore.username,
                    "quarkus.datasource.password": metastore.password,
                }
            )

        return conf

    def to_dict(self) -> dict[str, str]:
        """Return the dict representation of the configuration file."""
        return self._base_conf

    @property
    def contents(self) -> str:
        """Return configuration contents formatted to be consumed by pebble layer."""
        dict_content = self.to_dict()

        return "\n".join(
            [
                f"{key}={value}"
                for key in sorted(dict_content.keys())
                if (value := dict_content[key])
            ]
        )
