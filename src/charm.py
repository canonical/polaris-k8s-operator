#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Apache Polaris Kubernetes charm."""

import logging
import warnings
from typing import cast

from pydantic.warnings import UnsupportedFieldAttributeWarning

warnings.filterwarnings("ignore", category=UnsupportedFieldAttributeWarning)

import ops
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from data_platform_helpers.advanced_statuses.handler import StatusHandler
from data_platform_helpers.advanced_statuses.models import StatusObject
from data_platform_helpers.advanced_statuses.protocol import ManagerStatusProtocol
from data_platform_helpers.advanced_statuses.types import Scope

from core.constants import (
    MONITORING_PORT,
    POLARIS_CONTAINER_NAME,
)
from core.context import Context
from core.workload.polaris import PolarisWorkload
from events.metastore import MetastoreEvents
from events.polaris import CharmStatuses, PolarisEvents
from events.s3 import S3Events
from protocols import CharmWithStatus

logger = logging.getLogger(__name__)


class PolarisWorkloadStatus(ManagerStatusProtocol):
    """Report generic low-priority Polaris workload statuses."""

    def __init__(self, context: Context, polaris_workload: PolarisWorkload) -> None:
        self.name = "polaris-workload"
        self.state = context
        self.polaris_workload = polaris_workload

    def get_statuses(self, scope: Scope, recompute: bool = False) -> list[StatusObject]:
        """Return low-priority workload statuses."""
        if not self.polaris_workload.active:
            return [CharmStatuses.NOT_RUNNING]
        return []


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
        self.s3_events = S3Events(cast(CharmWithStatus, self), self.context, self.polaris_workload)
        self.polaris_workload_status = PolarisWorkloadStatus(self.context, self.polaris_workload)

        self.status = StatusHandler(
            self,
            self.polaris_events,
            self.metastore_events,
            self.s3_events,
            self.polaris_workload_status,
        )

        self.log_forwarder = LogForwarder(self)
        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[
                {
                    "metrics_path": "/q/metrics",
                    "static_configs": [{"targets": [f"*:{MONITORING_PORT}"]}],
                }
            ],
        )
        self.grafana_dashboards = GrafanaDashboardProvider(self)


if __name__ == "__main__":  # pragma: nocover
    ops.main(PolarisK8sCharm)
