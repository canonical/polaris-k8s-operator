#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Apache Polaris Kubernetes charm."""

import logging
import warnings

import ops
from data_platform_helpers.advanced_statuses.handler import StatusHandler
from pydantic.warnings import UnsupportedFieldAttributeWarning

warnings.filterwarnings("ignore", category=UnsupportedFieldAttributeWarning)
from core.constants import POLARIS_CONTAINER_NAME
from core.context import Context
from core.workload.polaris import PolarisWorkload
from events.metastore import MetastoreEvents
from events.polaris import PolarisEvents
from events.s3 import S3Events

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

        # Events
        self.polaris_events = PolarisEvents(self, self.context, self.polaris_workload)
        self.metastore_events = MetastoreEvents(self, self.context, self.polaris_workload)
        self.s3_events = S3Events(self, self.context, self.polaris_workload)

        self.status = StatusHandler(
            self,
            self.polaris_events,
            self.metastore_events,
            self.s3_events,
        )


if __name__ == "__main__":  # pragma: nocover
    ops.main(PolarisK8sCharm)
