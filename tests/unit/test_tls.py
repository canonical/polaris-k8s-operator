# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import cast

from core.constants import OBJECT_STORAGE_CERTIFICATE
from core.context import Context
from core.workload.polaris import PolarisWorkload
from managers.tls import TLSManager

CERTIFICATE_1 = """-----BEGIN CERTIFICATE-----
MIIBtest-certificate-1
-----END CERTIFICATE-----"""
CERTIFICATE_2 = """-----BEGIN CERTIFICATE-----
MIIBtest-certificate-2
-----END CERTIFICATE-----"""


class TestUnitServerBag:
    def __init__(self, truststore_password: str = "") -> None:
        self.truststore_password = truststore_password

    def set_truststore_password(self, password: str) -> None:
        self.truststore_password = password


class TestTLSContext:
    def __init__(self, truststore_password: str = "") -> None:
        self.unit_server = TestUnitServerBag(truststore_password)


class TestWorkload:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.aliases: set[str] = set()

    def ensure_truststore_initialized(self, password: str) -> bool:
        return False

    def truststore_aliases(self, password: str) -> list[str]:
        return sorted(self.aliases)

    def delete_truststore_aliases_by_prefix(self, alias_prefix: str, password: str) -> bool:
        deleted = False
        for alias in list(self.aliases):
            if alias.startswith(alias_prefix):
                self.aliases.remove(alias)
                deleted = True
        return deleted

    def ensure_file(self, path: str, content: str) -> bool:
        changed = self.files.get(path) != content
        self.files[path] = content
        return changed

    def import_ca_certificate(self, password: str, alias: str, certificate_path: str) -> None:
        self.aliases.add(alias)

    def remove_file(self, path: str) -> bool:
        return self.files.pop(path, None) is not None


def test_tls_manager_is_idempotent_for_multi_certificate_chain() -> None:
    # Given
    workload = TestWorkload()
    manager = TLSManager(
        cast(Context, TestTLSContext(truststore_password="truststore-password")),
        cast(PolarisWorkload, workload),
    )

    # When
    first = manager.ensure_certificates_imported(
        [CERTIFICATE_1, CERTIFICATE_2],
        "object-storage-ca",
        OBJECT_STORAGE_CERTIFICATE,
    )
    second = manager.ensure_certificates_imported(
        [CERTIFICATE_1, CERTIFICATE_2],
        "object-storage-ca",
        OBJECT_STORAGE_CERTIFICATE,
    )
    third = manager.ensure_certificates_imported(
        [CERTIFICATE_1, CERTIFICATE_2],
        "oauth-ca",  # Different kind, should be flagged
        OBJECT_STORAGE_CERTIFICATE,
    )

    # Then
    assert first is True
    assert second is False
    assert third is True
