# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Polaris workload configuration."""

from core.constants import (
    POLARIS_TRUSTSTORE,
    REALM,
    ROOT_PRINCIPAL_ID,
    SYMMETRIC_KEY,
)
from core.context import Context
from core.logging import WithLogging


class PolarisConfig(WithLogging):
    """Polaris configuration."""

    def __init__(self, context: Context) -> None:
        self.context = context

    @property
    def bootstrap_credentials(self) -> str:
        """Polaris root principal credentials."""
        return f"{REALM},{ROOT_PRINCIPAL_ID},{self.context.cluster.admin_password}"

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

        return conf | self._oauth_conf

    @property
    def service_environment(self) -> dict[str, str]:
        """Return environment variables for the Polaris service."""
        env = {"JAVA_TOOL_OPTIONS": ""}

        s3 = self.context.s3
        if s3.ready:
            env.update(
                {
                    "AWS_ACCESS_KEY_ID": s3.access_key,
                    "AWS_SECRET_ACCESS_KEY": s3.secret_key,
                    "AWS_REGION": s3.region,
                    "AWS_DEFAULT_REGION": s3.region,
                }
            )

        if java_tool_options := self.java_tool_options:
            env["JAVA_TOOL_OPTIONS"] = java_tool_options

        return env

    @property
    def java_tool_options(self) -> str:
        """Return JVM options required by Polaris integrations."""
        if truststore_password := self.context.unit_server.truststore_password:
            return " ".join(
                (
                    f"-Djavax.net.ssl.trustStore={POLARIS_TRUSTSTORE}",
                    f"-Djavax.net.ssl.trustStorePassword={truststore_password}",
                )
            )
        return ""

    @property
    def _oauth_conf(self) -> dict[str, str]:
        """Return the minimal OAuth/OIDC authentication configuration for Polaris."""
        if not self.context.oauth.ready:
            return {}

        return {
            "polaris.authentication.type": "mixed",
            "quarkus.oidc.tenant-enabled": "true",
            "quarkus.oidc.auth-server-url": self.context.oauth.issuer_url,
            "polaris.oidc.principal-mapper.type": "default",
            "polaris.oidc.principal-mapper.name-claim-path": "sub",
            "quarkus.oidc.roles.role-claim-path": "scp",
            "polaris.oidc.principal-roles-mapper.type": "default",
            "polaris.oidc.principal-roles-mapper.filter": ".+",
            "polaris.oidc.principal-roles-mapper.mappings[0].regex": "^.*$",
            "polaris.oidc.principal-roles-mapper.mappings[0].replacement": "PRINCIPAL_ROLE:ALL",
        }

    @property
    def _s3_conf(self) -> dict[str, str]:
        """Return S3-compatible object storage configurations."""
        s3 = self.context.s3
        if not s3.ready:
            return {}

        return {
            'polaris.features."SUPPORTED_CATALOG_STORAGE_TYPES"': '["S3"]',
            "polaris.storage.aws.access-key": s3.access_key,
            "polaris.storage.aws.secret-key": s3.secret_key,
        }

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
