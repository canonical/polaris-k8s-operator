# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""File containing all possible statuses for the Polaris charm."""

from enum import Enum

from data_platform_helpers.advanced_statuses.models import StatusObject


class CharmStatuses(Enum):
    """Generic status objects related to the charm."""

    ACTIVE_IDLE = StatusObject(status="active", message="")
    WAITING_PEBBLE = StatusObject(status="maintenance", message="Waiting for Pebble")


class ConfigStatuses(Enum):
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
