# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Polaris workload configuration."""

from core.constants import ADMIN_USER, OBJECT_STORAGE_TRUSTSTORE, REALM, SYMMETRIC_KEY
from core.context import Context
from core.logging import WithLogging


class PolarisConfig(WithLogging):
    """Polaris configuration."""

    def __init__(self, context: Context) -> None:
        self.context = context

    @property
    def bootstrap_credentials(self) -> str:
        """Polaris root principal credentials."""
        return f"{REALM},{ADMIN_USER},{self.context.cluster.admin_password}"

    @property
    def _base_conf(self) -> dict[str, str]:
        """Base Polaris configurations."""
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

    @property
    def service_environment(self) -> dict[str, str]:
        """Return environment variables for the Polaris service."""
        truststore_password = self.context.unit_server.truststore_password
        if not self.context.s3.has_custom_ca or not truststore_password:
            return {"JAVA_TOOL_OPTIONS": ""}

        return {
            "JAVA_TOOL_OPTIONS": " ".join(
                (
                    f"-Djavax.net.ssl.trustStore={OBJECT_STORAGE_TRUSTSTORE}",
                    f"-Djavax.net.ssl.trustStorePassword={truststore_password}",
                )
            )
        }

    @property
    def _s3_conf(self) -> dict[str, str]:
        """Return S3-compatible object storage configurations."""
        s3 = self.context.s3
        if not s3.ready:
            return {}

        conf = {
            'polaris.features."SUPPORTED_CATALOG_STORAGE_TYPES"': '["S3"]',
            "polaris.storage.aws.access-key": s3.access_key,
            "polaris.storage.aws.secret-key": s3.secret_key,
            "s3.client.region": s3.region,
            "s3.endpoint": s3.endpoint,
        }

        if s3.uri_style:
            conf["s3.path-style-access"] = str(s3.uri_style == "path")

        return conf

    def to_dict(self) -> dict[str, str]:
        """Return the dict representation of the configuration file."""
        return self._base_conf | self._s3_conf

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
