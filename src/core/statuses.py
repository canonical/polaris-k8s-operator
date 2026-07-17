# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""File containing all possible statuses for the Polaris charm."""

from data_platform_helpers.advanced_statuses.models import StatusObject


class _CharmStatuses:
    """Generic status objects related to the charm."""

    ACTIVE_IDLE = StatusObject(status="active", message="")
    NOT_RUNNING = StatusObject(status="maintenance", message="Polaris is not serving requests")
    ROTATING_ROOT_PRINCIPAL_CREDENTIALS = StatusObject(
        status="maintenance",
        message="Rotating Polaris root principal credentials",
        running="blocking",
    )
    SYSTEM_USER_SECRET_DOES_NOT_EXIST = StatusObject(
        status="blocked", message="Secret provided as system-user does not exist"
    )
    SYSTEM_USER_SECRET_INSUFFICIENT_PERMISSION = StatusObject(
        status="blocked",
        message="Secret provided as system-user has not been granted to the charm",
    )
    SYSTEM_USER_SECRET_INVALID = StatusObject(
        status="blocked", message="Secret provided as system-user has invalid content"
    )
    WAITING_PEBBLE = StatusObject(status="maintenance", message="Waiting for Pebble")


CharmStatuses = _CharmStatuses()


class _ConfigStatuses:
    """Status objects related to config options."""

    @staticmethod
    def missing_config_parameters(fields: list[str]) -> StatusObject:
        """Missing configuration values."""
        fields_str = ", ".join(f"'{field}'" for field in fields)
        return StatusObject(
            status="blocked",
            message=f"Missing config(s): {fields_str}",
            action=f"Set config(s): {fields_str}",
        )

    @staticmethod
    def invalid_config_parameters(fields: list[str]) -> StatusObject:
        """Invalid configuration values."""
        fields_str = ", ".join(f"'{field}'" for field in fields)
        return StatusObject(
            status="blocked",
            message=f"Invalid config(s): {fields_str}",
            action=f"Fix invalid config(s): {fields_str}",
        )


ConfigStatuses = _ConfigStatuses()


class _MetastoreStatuses:
    """Status objects related to the metastore integration."""

    METASTORE_RELATION_MISSING = StatusObject(
        status="blocked",
        message="Missing mandatory metastore relation",
        action="Relate the charm to a PostgreSQL database using the metastore endpoint",
    )
    METASTORE_NOT_READY = StatusObject(
        status="waiting",
        message="Waiting for metastore relation data",
    )

    @staticmethod
    def provider_error(message: str, resolution: str) -> StatusObject:
        """Return a status for fatal provider-side metastore errors."""
        return StatusObject(
            status="blocked",
            message=message,
            action=resolution,
        )


MetastoreStatuses = _MetastoreStatuses()


class _ObjectStorageStatuses:
    """Status objects related to the object storage integration."""

    OBJECT_STORAGE_RELATION_MISSING = StatusObject(
        status="blocked",
        message="Missing mandatory object storage relation",
        action="Relate the charm to an object storage integrator",
    )
    OBJECT_STORAGE_NOT_READY = StatusObject(
        status="waiting",
        message="Waiting for object storage relation data",
    )
    IMPORTING_OBJECT_STORAGE_CA = StatusObject(
        status="maintenance",
        message="Importing object storage CA certificate",
        running="blocking",
    )

    @staticmethod
    def missing_parameters(fields: list[str]) -> StatusObject:
        """Return a status for missing object storage relation data."""
        fields_str = ", ".join(f"'{field}'" for field in fields)
        return StatusObject(
            status="waiting",
            message=f"Missing object storage parameter(s): {fields_str}",
            action=f"Set object storage parameter(s): {fields_str}",
        )


ObjectStorageStatuses = _ObjectStorageStatuses()
