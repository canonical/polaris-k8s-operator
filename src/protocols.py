# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module containing protocols to satisfy type checking."""

from typing import Protocol

import ops
from data_platform_helpers.advanced_statuses.handler import StatusHandler


class HasStatusProtocol(Protocol):
    """Type checks if the charm uses advanced statuses."""

    status: StatusHandler


class CharmWithStatus(ops.CharmBase, HasStatusProtocol):
    """Merges ops class with protocol."""

    pass
