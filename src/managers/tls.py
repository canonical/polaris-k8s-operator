# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""TLS manager."""

import ipaddress
import secrets
import string
from typing import cast

import ops
from charmlibs.interfaces.tls_certificates import CertificateRequestAttributes

from core.constants import TLS_RELATION_NAME
from core.context import Context
from core.logging import WithLogging
from core.workload.polaris import PolarisWorkload


class TLSManager(WithLogging):
    """Manage TLS material.

    This manager currently serves two distinct purposes:
    - object-storage truststore management for the Polaris workload container
    - certificate request building for the console TLS integration
    """

    def __init__(self, context: Context, polaris_workload: PolarisWorkload) -> None:
        self.context = context
        self.polaris_workload = polaris_workload

    @staticmethod
    def generate_password() -> str:
        """Create a random truststore password."""
        return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

    def truststore_password(self) -> str:
        """Return this unit's truststore password."""
        if not self.context.unit_server.truststore_password:
            self.logger.info("Generating new truststore password")
            password = self.generate_password()
            self.context.unit_server.set_truststore_password(password)
            return password

        return self.context.unit_server.truststore_password

    def ensure_ca_chain_imported(self, ca_chain: list[str]) -> bool:
        """Import an object-storage CA chain into the Polaris workload truststore.

        The boolean return type indicates if the Polaris workload should be restarted.
        """
        if not ca_chain:
            return self.reset()

        self.polaris_workload.reset_object_storage_tls()
        password = self.truststore_password()
        try:
            for index, certificate in enumerate(ca_chain):
                self.polaris_workload.import_ca(
                    certificate,
                    password,
                    alias=f"object-storage-ca-{index}",
                )
        except ops.pebble.ExecError as e:
            if e.stdout and "already exists" in e.stdout:
                return False
            self.logger.error(e.stdout)
            raise

        self.logger.info("Object storage CA chain imported successfully")
        return True

    def reset(self) -> bool:
        """Remove object-storage TLS files from the Polaris workload."""
        self.logger.info("Deleting object storage TLS files")
        return self.polaris_workload.reset_object_storage_tls()

    def build_console_common_name(self) -> str:
        """Return the common name for the console TLS integration certificate request."""
        return f"{self.context.unit_server.unit_name.replace('/', '')}-{self.context.model.uuid}"

    def build_console_sans_ip(self) -> frozenset[str]:
        """Return IP SANs for the console TLS integration certificate request."""
        sans_ip: set[str] = set()
        try:
            network = self.context.model.get_binding(TLS_RELATION_NAME).network
        except ops.ModelError:
            return frozenset()

        for candidate in (network.ingress_address, network.bind_address):
            if not candidate:
                continue
            try:
                sans_ip.add(str(ipaddress.ip_address(cast(str, candidate))))
            except ValueError:
                continue

        return frozenset(sans_ip)

    def build_console_sans_dns(self) -> frozenset[str]:
        """Return DNS SANs for the console TLS integration certificate request."""
        unit_name = self.context.unit_server.unit_name.replace("/", "-")
        app_name = self.context.model.app.name
        model_name = self.context.model.name

        return frozenset(
            {
                f"{unit_name}.{app_name}-endpoints.{model_name}.svc.cluster.local",
            }
        )

    def build_console_certificate_request(self) -> CertificateRequestAttributes:
        """Build a certificate request for the console TLS integration."""
        return CertificateRequestAttributes(
            common_name=self.build_console_common_name(),
            sans_dns=self.build_console_sans_dns(),
            sans_ip=self.build_console_sans_ip(),
        )
