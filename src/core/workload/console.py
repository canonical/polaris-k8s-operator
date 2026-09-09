# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module containing all business logic related to the Polaris Console workload."""

import ops.pebble
from charmlibs import pathops
from ops.model import Container

from core.constants import CONSOLE_SERVICE_NAME, CONSOLE_TLS_CERTIFICATE, CONSOLE_TLS_PRIVATE_KEY
from core.logging import WithLogging


class ConsoleWorkload(WithLogging):
    """Represent the Polaris Console workload on Kubernetes."""

    def __init__(self, container: Container) -> None:
        self.container = container
        self.fs = pathops.ContainerPath("/", container=container)

    def _console_layer(self, environment: dict[str, str] | None = None) -> ops.pebble.LayerDict:
        # TODO: handle environment
        layer: ops.pebble.LayerDict = {
            "services": {
                CONSOLE_SERVICE_NAME: {
                    "override": "merge",
                    "startup": "enabled",
                    "on-failure": "restart",
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
            service = self.container.get_service(CONSOLE_SERVICE_NAME)
        except ops.pebble.ConnectionError:
            self.logger.debug(f"Service {CONSOLE_SERVICE_NAME} not running")
            return False
        return service.is_running()

    def tls_assets_present(self) -> bool:
        """Return whether both console TLS assets are present."""
        return (self.fs / CONSOLE_TLS_CERTIFICATE).exists() and (
            self.fs / CONSOLE_TLS_PRIVATE_KEY
        ).exists()

    def write_tls_assets(self, certificate: str, private_key: str) -> bool:
        """Write console TLS certificate and private key.

        Returns whether the local TLS asset contents changed.
        """
        certificate_changed = pathops.ensure_contents(
            self.fs / CONSOLE_TLS_CERTIFICATE,
            certificate,
        )
        private_key_changed = pathops.ensure_contents(
            self.fs / CONSOLE_TLS_PRIVATE_KEY,
            private_key,
        )
        return certificate_changed or private_key_changed

    def remove_tls_assets(self) -> bool:
        """Remove console TLS certificate and private key."""
        removed = False
        for path in (CONSOLE_TLS_CERTIFICATE, CONSOLE_TLS_PRIVATE_KEY):
            try:
                (self.fs / path).unlink()
                removed = True
            except FileNotFoundError:
                continue
        return removed

    def restart(self, environment: dict[str, str] | None = None) -> None:
        """Restart the workload service."""
        self.stop()
        self.start(environment=environment)

    def start(self, environment: dict[str, str] | None = None) -> None:
        """Execute business logic for starting the workload."""
        self.container.add_layer(
            CONSOLE_SERVICE_NAME,
            self._console_layer(environment=environment),
            combine=True,
        )
        self.container.start(CONSOLE_SERVICE_NAME)

    def stop(self) -> None:
        """Execute business logic for stopping the workload."""
        if self.ready and CONSOLE_SERVICE_NAME in self.container.get_services():
            self.container.stop(CONSOLE_SERVICE_NAME)
