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

    def update(self) -> None:
        """Update Polaris Console service and restart it."""
        console_tls = self.context.console_tls
        if console_tls.ready:
            changed = self.workload.ensure_tls_assets(
                console_tls.certificate,
                console_tls.private_key,
            )
        else:
            changed = self.workload.remove_tls_assets()

        if not self.workload.active:
            self.logger.warning("starting console")
            self.workload.start()
            return

        if changed:
            self.logger.info("Restarting console to apply configuration changes")
            self.workload.restart()
