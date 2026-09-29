# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Console manager."""

from core.constants import OAUTH_CALLBACK_PATH
from core.context import Context
from core.logging import WithLogging
from core.workload.console import ConsoleWorkload


class ConsoleManager(WithLogging):
    """Manage Polaris Console workload configuration and restarts."""

    def __init__(self, context: Context, workload: ConsoleWorkload) -> None:
        self.context = context
        self.workload = workload

    def environment(self) -> dict[str, str]:
        """Return the environment required by the Console workload."""
        environment = {
            "VITE_OIDC_ISSUER_URL": "",
            "VITE_OIDC_CLIENT_ID": "",
            "VITE_OIDC_REDIRECT_URI": "",
            "VITE_OIDC_SCOPE": "",
        }
        if self.context.oauth.ready and self.context.ingress_url:
            environment.update(
                {
                    "VITE_OIDC_ISSUER_URL": self.context.oauth.issuer_url,
                    "VITE_OIDC_CLIENT_ID": self.context.oauth.client_id,
                    "VITE_OIDC_REDIRECT_URI": f"{self.context.ingress_url}{OAUTH_CALLBACK_PATH}",
                    "VITE_OIDC_SCOPE": self.context.oauth.scope,
                }
            )
        return environment

    def update(self) -> None:
        """Update Polaris Console service and restart it."""
        environment = self.environment()
        changed = self.workload.current_environment() != environment

        console_tls = self.context.console_tls
        if console_tls.ready:
            changed = (
                self.workload.ensure_tls_assets(
                    console_tls.certificate,
                    console_tls.private_key,
                )
                or changed
            )
        else:
            changed = self.workload.remove_tls_assets() or changed

        if not self.workload.active:
            self.logger.warning("starting console")
            self.workload.start(environment=environment)
            return

        if changed:
            self.logger.info("Restarting console to apply configuration changes")
            self.workload.restart(environment=environment)
