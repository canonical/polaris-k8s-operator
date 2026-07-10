#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Apache Polaris Kubernetes charm."""

import logging

import ops
from data_platform_helpers.advanced_statuses.handler import StatusHandler

from core.constants import POLARIS_CONTAINER_NAME
from core.context import Context
from core.workload.polaris import PolarisWorkload
from events.polaris import PolarisEvents

logging.captureWarnings(True)
py_warnings_logger = logging.getLogger("py.warnings")


class _PydanticWarningFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if "UnsupportedFieldAttributeWarning" in record.getMessage():
            return False
        return True


py_warnings_logger.addFilter(_PydanticWarningFilter())
logger = logging.getLogger(__name__)


class PolarisK8sCharm(ops.CharmBase):
    """Manage Apache Polaris on Kubernetes."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        # Workloads
        self.polaris_workload = PolarisWorkload(
            container=self.unit.get_container(POLARIS_CONTAINER_NAME),
        )
        # TODO(console): Add console_workload

        # Context
        self.context = Context(self)

        # Event
        self.polaris_events = PolarisEvents(self, self.context, self.polaris_workload)

        self.status = StatusHandler(
            self,
            self.polaris_events,
        )


if __name__ == "__main__":  # pragma: nocover
    ops.main(PolarisK8sCharm)
