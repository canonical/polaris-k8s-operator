# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module containing all business logic related to the workload."""

import re

import ops.pebble
import yaml
from charmlibs import pathops
from ops.model import Container

from core.constants import (
    DEFAULT_JAVA_TRUSTSTORE,
    DEFAULT_JAVA_TRUSTSTORE_PASSWORD,
    KEYTOOL,
    POLARIS_APPLICATION_PROPERTIES,
    POLARIS_BOOTSTRAP_COMMAND,
    POLARIS_SERVICE_NAME,
    POLARIS_TRUSTSTORE,
    ROCK_METADATA,
    WORKLOAD_GROUP,
    WORKLOAD_USER,
)
from core.logging import WithLogging


class PolarisWorkload(WithLogging):
    """Represent the Polaris workload on Kubernetes."""

    def __init__(self, container: Container) -> None:
        self.container = container
        self.fs = pathops.ContainerPath("/", container=container)

    def _polaris_layer(self, environment: dict[str, str] | None = None) -> ops.pebble.LayerDict:
        service_environment = {
            "QUARKUS_CONFIG_LOCATIONS": f"file://{POLARIS_APPLICATION_PROPERTIES}"
        } | (environment or {})
        layer: ops.pebble.LayerDict = {
            "services": {
                POLARIS_SERVICE_NAME: {
                    "override": "merge",
                    "startup": "enabled",
                    "on-failure": "restart",
                    "environment": service_environment,
                }
            }
        }
        return layer

    @property
    def ready(self) -> bool:
        """Check whether the service is ready to be used."""
        return self.container.can_connect()

    @property
    def active(self) -> bool:
        """Return the health of the service."""
        try:
            service = self.container.get_service(POLARIS_SERVICE_NAME)
        except ops.pebble.ConnectionError:
            self.logger.debug(f"Service {POLARIS_SERVICE_NAME} not running")
            return False
        return service.is_running()

    def restart(self, environment: dict[str, str] | None = None) -> None:
        """Restart the workload service."""
        self.stop()
        self.start(environment=environment)

    def start(self, environment: dict[str, str] | None = None) -> None:
        """Execute business logic for starting the workload."""
        self.container.add_layer(
            POLARIS_SERVICE_NAME,
            self._polaris_layer(environment=environment),
            combine=True,
        )
        self.container.start(POLARIS_SERVICE_NAME)

    def stop(self) -> None:
        """Execute business logic for stopping the workload."""
        if self.ready and POLARIS_SERVICE_NAME in self.container.get_services():
            self.container.stop(POLARIS_SERVICE_NAME)

    def ensure_truststore_initialized(self, password: str) -> bool:
        """Create the Polaris truststore from the default JVM truststore if missing."""
        if (self.fs / POLARIS_TRUSTSTORE).exists():
            return False

        self.container.exec(["cp", DEFAULT_JAVA_TRUSTSTORE, POLARIS_TRUSTSTORE]).wait_output()
        self.container.exec(
            ["chown", "-R", f"{WORKLOAD_USER}:{WORKLOAD_GROUP}", POLARIS_TRUSTSTORE]
        ).wait_output()
        self.container.exec(["chmod", "660", POLARIS_TRUSTSTORE]).wait_output()
        self.container.exec(
            [
                KEYTOOL,
                "-storepasswd",
                "-new",
                password,
                "-keystore",
                POLARIS_TRUSTSTORE,
                "-storepass",
                DEFAULT_JAVA_TRUSTSTORE_PASSWORD,
            ]
        ).wait_output()
        return True

    def import_ca_certificate(
        self,
        password: str,
        alias: str,
        certificate_path: str,
    ) -> None:
        """Import a CA certificate into the Polaris truststore."""
        process = self.container.exec(
            [
                KEYTOOL,
                "-import",
                "-v",
                "-alias",
                alias,
                "-file",
                certificate_path,
                "-keystore",
                POLARIS_TRUSTSTORE,
                "-storepass",
                password,
                "-noprompt",
            ]
        )
        process.wait_output()

    def truststore_aliases(self, password: str) -> list[str]:
        """Return aliases currently present in the Polaris truststore."""
        try:
            process = self.container.exec(
                [
                    KEYTOOL,
                    "-list",
                    "-v",
                    "-keystore",
                    POLARIS_TRUSTSTORE,
                    "-storepass",
                    password,
                ]
            )
            stdout, _ = process.wait_output()
        except ops.pebble.ExecError as e:
            stderr = e.stderr or ""
            stdout = e.stdout or ""
            if "No such file or directory" in stderr or "Keystore file does not exist" in stdout:
                return []
            raise
        return re.findall(r"^Alias name: (.+)$", stdout, flags=re.MULTILINE)

    def delete_truststore_alias(
        self,
        alias: str,
        password: str,
    ) -> None:
        """Delete one alias from the Polaris truststore."""
        process = self.container.exec(
            [
                KEYTOOL,
                "-delete",
                "-alias",
                alias,
                "-keystore",
                POLARIS_TRUSTSTORE,
                "-storepass",
                password,
                "-noprompt",
            ]
        )
        process.wait_output()

    def delete_truststore_aliases_by_prefix(
        self,
        alias_prefix: str,
        password: str,
    ) -> bool:
        """Delete all truststore aliases matching the given prefix."""
        deleted = False
        for alias in self.truststore_aliases(password):
            if not alias.startswith(alias_prefix):
                continue
            self.delete_truststore_alias(alias, password)
            deleted = True
        return deleted

    def ensure_file(self, path: str, content: str) -> bool:
        """Ensure a file has the expected content."""
        return pathops.ensure_contents(self.fs / path, content)

    def remove_file(self, path: str) -> bool:
        """Remove one file from the workload."""
        try:
            (self.fs / path).unlink()
        except FileNotFoundError:
            return False
        return True

    def bootstrap_metastore(self, realm: str, bootstrap_credentials: str) -> None:
        """Bootstrap the Polaris metastore.

        Quarkus applications default to listening on 8080, that we want to avoid because
        of the console container in the same pod.
        """
        try:
            process = self.container.exec(
                [*POLARIS_BOOTSTRAP_COMMAND, f"-r={realm}", f"-c={bootstrap_credentials}"],
                environment={
                    "QUARKUS_CONFIG_LOCATIONS": f"file://{POLARIS_APPLICATION_PROPERTIES}",
                    "POLARIS_JAVA_OPTS": "-Dquarkus.http.port=0 -Dquarkus.management.port=0",
                },
            )
            stdout, stderr = process.wait_output()
        except ops.pebble.ExecError as e:
            self.logger.error(
                "Failed to bootstrap Polaris metastore: stdout=%s stderr=%s",
                e.stdout,
                e.stderr,
            )
            raise

        if stdout:
            self.logger.debug("Metastore bootstrap output: %s", stdout)
        if stderr:
            self.logger.debug("Metastore bootstrap error output: %s", stderr)

    def get_workload_version(self) -> str:
        """Get Polaris version from the workload."""
        try:
            metadata = (self.fs / ROCK_METADATA).read_text()
            version = yaml.safe_load(metadata).get("version", "")
            return version

        except Exception:
            return ""
