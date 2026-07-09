# Copyright 2026 Canonical Limited
# See LICENSE file for licensing details.

"""Polaris manager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from charmlibs import pathops

from config.polaris import PolarisConfig
from core.constants import POLARIS_APPLICATION_PROPERTIES, SYMMETRIC_KEY
from core.context import Context
from core.logging import WithLogging
from core.workload.polaris import PolarisWorkload

if TYPE_CHECKING:
    from charm import PolarisK8sCharm


class PolarisManager(WithLogging):
    """Kyuubi manager class."""

    def __init__(
        self,
        charm: PolarisK8sCharm,
        context: Context,
        workload: PolarisWorkload,
    ):
        self.charm = charm
        self.context = context
        self.workload = workload

    def update(
        self,
    ) -> None:
        """Update Polaris service and restart it."""
        if not self.context.cluster.ready:
            self.logger.info("Skipping workload restart")
            return

        self.logger.info("Restarting Polaris workload")

        should_restart = any(
            (
                pathops.ensure_contents(
                    self.workload.fs / POLARIS_APPLICATION_PROPERTIES,
                    PolarisConfig(
                        context=self.context,
                    ).contents,
                ),
                pathops.ensure_contents(
                    self.workload.fs / SYMMETRIC_KEY,
                    self.context.cluster.shared_key,
                ),
            )
        )

        if not should_restart:
            self.logger.info("Workload restart skipped because the configuration did not change.")
            return
        self.workload.restart()
