# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""TLS manager."""

import secrets
import string

import ops

from core.context import Context
from core.logging import WithLogging
from core.workload.polaris import PolarisWorkload


class TLSManager(WithLogging):
    """Manage TLS material for Polaris integrations."""

    def __init__(self, context: Context, workload: PolarisWorkload) -> None:
        self.context = context
        self.workload = workload

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

    def import_ca_chain(self, ca_chain: list[str]) -> bool:
        """Import a CA chain into the workload truststore."""
        if not ca_chain:
            return self.reset()

        self.workload.reset_object_storage_tls()
        password = self.truststore_password()
        try:
            for index, certificate in enumerate(ca_chain):
                self.workload.import_ca(certificate, password, alias=f"object-storage-ca-{index}")
        except ops.pebble.ExecError as e:
            if e.stdout and "already exists" in e.stdout:
                return False
            self.logger.error(e.stdout)
            raise

        self.logger.info("Object storage CA chain imported successfully")
        return True

    def reset(self) -> bool:
        """Remove object storage TLS files."""
        self.logger.info("Deleting object storage TLS files")
        self.workload.reset_object_storage_tls()
        return True
