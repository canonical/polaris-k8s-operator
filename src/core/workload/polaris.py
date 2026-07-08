#!/usr/bin/env python3
# Copyright 2024 Canonical Limited
# See LICENSE file for licensing details.

"""Module containing all business logic related to the workload."""

import ops.pebble
from charmlibs import pathops
from ops.model import Container

from core.constants import (
    POLARIS_APPLICATION_PROPERTIES,
    POLARIS_SERVICE_NAME,
)
from core.logging import WithLogging


class PolarisWorkload(WithLogging):
    """Class representing workload implementation for Polaris on K8s."""

    def __init__(self, container: Container):
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
        """Restarts the workload service."""
        self.stop()
        self.start()

    def start(self):
        """Execute business-logic for starting the workload."""
        self.container.add_layer(POLARIS_SERVICE_NAME, self._base_polaris_layer, combine=True)
        self.container.restart(POLARIS_SERVICE_NAME)

    def stop(self):
        """Execute business-logic for stopping the workload."""
        if self.ready and POLARIS_SERVICE_NAME in self.container.get_services():
            self.container.stop(POLARIS_SERVICE_NAME)
