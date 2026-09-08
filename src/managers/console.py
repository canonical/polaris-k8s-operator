# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Console manager."""

from core.context import Context
from core.logging import WithLogging
from core.workload.console import ConsoleWorkload


class ConsoleManager(WithLogging):
    """Manage Polaris Console workload configuration and restarts."""

    def __init__(self, context: Context, workload: ConsoleWorkload) -> None:
        self.context = context
        self.workload = workload

    def update(
        self,
        force_restart: bool = False,
    ) -> None:
        """Update Polaris Console service and restart it."""
        # TODO: handle TLS file writing
        if not self.workload.active:
            self.logger.warning("starting console")
            self.workload.start()
