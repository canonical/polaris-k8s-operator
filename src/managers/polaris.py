# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Polaris manager."""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING

from apache_polaris.cli.api_client_builder import ApiClientBuilder
from apache_polaris.cli.constants import DEFAULT_HEADER
from apache_polaris.sdk.management.api import PolarisDefaultApi
from apache_polaris.sdk.management.models.reset_principal_request import ResetPrincipalRequest
from charmlibs import pathops
from ops import CharmBase

from config.polaris import PolarisConfig
from core.constants import (
    ADMIN_USER,
    POLARIS_APPLICATION_PROPERTIES,
    REALM,
    REST_PORT,
    SYMMETRIC_KEY,
)
from core.context import Context
from core.logging import WithLogging
from core.workload.polaris import PolarisWorkload


class PolarisManager(WithLogging):
    """Manage Polaris workload configuration and restarts."""

    def __init__(
        self,
        charm: CharmBase,
        context: Context,
        workload: PolarisWorkload,
    ) -> None:
        self.charm = charm
        self.context = context
        self.workload = workload

    def _api(self, client_secret: str) -> PolarisDefaultApi:
        """Return an authenticated Polaris management API object."""
        options = Namespace(
            proxy=None,
            access_token=None,
            profile=None,
            base_url=f"http://localhost:{REST_PORT}",
            host=None,
            port=None,
            client_id=ADMIN_USER,
            client_secret=client_secret,
            realm=REALM,
            header=DEFAULT_HEADER,
        )
        api_client = ApiClientBuilder(options).get_api_client()
        return PolarisDefaultApi(api_client)

    def _root_principal_name(self, api: PolarisDefaultApi) -> str:
        """Return the principal name associated with the root client id."""
        for principal in api.list_principals().principals:
            if principal.client_id == ADMIN_USER:
                return principal.name

        raise ValueError(f"Could not find Polaris principal with client id {ADMIN_USER}")

    def reset_root_principal_credentials(self, current_password: str, new_password: str) -> None:
        """Reset root principal credentials through the Polaris management API."""
        api = self._api(client_secret=current_password)
        api.reset_credentials(
            self._root_principal_name(api),
            ResetPrincipalRequest(clientId=ADMIN_USER, clientSecret=new_password),
        )

    def update(
        self,
        force_restart: bool = False,
    ) -> None:
        """Update Polaris service and restart it."""
        if not self.context.cluster.ready:
            self.logger.info("Skipping workload restart")
            return

        if not self.context.metastore.ready:
            self.logger.info("Skipping workload restart, metastore is not ready")
            return

        if not self.context.s3.ready:
            self.logger.info("Skipping workload restart, object storage is not ready")
            return

        self.logger.info("Restarting Polaris workload")

        config = PolarisConfig(context=self.context)
        config_changed = any(
            (
                pathops.ensure_contents(
                    self.workload.fs / POLARIS_APPLICATION_PROPERTIES,
                    config.contents,
                ),
                pathops.ensure_contents(
                    self.workload.fs / SYMMETRIC_KEY,
                    self.context.cluster.shared_key,
                ),
            )
        )
        should_restart = force_restart or config_changed

        if not self.context.cluster.metastore_bootstrapped:
            if not self.charm.unit.is_leader():
                self.logger.info("Skipping workload restart, metastore is not bootstrapped")
                return
            # Note: Polaris 1.7.0 should make the bootstrap idempotent, so we might adapt
            # this part in the future
            self.workload.bootstrap_metastore(REALM, config.bootstrap_credentials)
            self.context.cluster.set_metastore_bootstrapped(True)
            should_restart = True

        if not should_restart:
            self.logger.info("Workload restart skipped because the configuration did not change.")
            return
        self.workload.restart(environment=config.service_environment)
