# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module containing all business logic related to the workload."""

import ops.pebble
import yaml
from charmlibs import pathops
from ops.model import Container

from core.constants import (
    POLARIS_APPLICATION_PROPERTIES,
    POLARIS_BOOTSTRAP_COMMAND,
    POLARIS_SERVICE_NAME,
    ROCK_METADATA,
)
from core.logging import WithLogging


class PolarisWorkload(WithLogging):
    """Represent the Polaris workload on Kubernetes."""

    def __init__(self, container: Container) -> None:
        self.container = container
        self.fs = pathops.ContainerPath("/", container=container)

    @property
    def _base_polaris_layer(self) -> ops.pebble.LayerDict:
        layer: ops.pebble.LayerDict = {
            "services": {
                POLARIS_SERVICE_NAME: {
                    "override": "merge",
                    "startup": "enabled",
                    "on-failure": "restart",
                    "environment": {
                        "QUARKUS_CONFIG_LOCATIONS": f"file://{POLARIS_APPLICATION_PROPERTIES}"
                    },
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

    def restart(self) -> None:
        """Restart the workload service."""
        self.stop()
        self.start()

    def start(self) -> None:
        """Execute business logic for starting the workload."""
        self.container.add_layer(POLARIS_SERVICE_NAME, self._base_polaris_layer, combine=True)
        self.container.restart(POLARIS_SERVICE_NAME)

    def stop(self) -> None:
        """Execute business logic for stopping the workload."""
        if self.ready and POLARIS_SERVICE_NAME in self.container.get_services():
            self.container.stop(POLARIS_SERVICE_NAME)

    def bootstrap_metastore(self, realm: str, bootstrap_credentials: str) -> None:
        """Bootstrap the Polaris metastore."""
        try:
            process = self.container.exec(
                [*POLARIS_BOOTSTRAP_COMMAND, f"-r={realm}", f"-c={bootstrap_credentials}"],
                environment={
                    "QUARKUS_CONFIG_LOCATIONS": f"file://{POLARIS_APPLICATION_PROPERTIES}",
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
