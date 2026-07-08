# Copyright 2026  Canonical Limited
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
    def _base_conf(self) -> dict[str, str]:  # noqa: E501
        """Return base Polaris configurations."""
        conf = {
            "polaris.bootstrap.credentials": f"{REALM},{ADMIN_USER},{self.context.cluster.admin_password}",  # noqa: E501
            "polaris.readiness.ignore-severe-issues": "true",
            "polaris.realm-context.realms": "POLARIS",
            "polaris.realm-context.require-header": "true",
            "polaris.authentication.token-broker.type": "symmetric-key",
            "polaris.authentication.token-broker.symmetric-key.file": SYMMETRIC_KEY,
        }

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
