# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module containing protocols to satisfy type checking."""

from typing import Protocol

import ops
from data_platform_helpers.advanced_statuses.handler import StatusHandler


class HasReconcileProtocol(Protocol):
    """Type checks if the charm has reconcile method."""

    def reconcile(self, handler: str) -> None:
        """Force-reconcile a specific domain handler."""
        ...


class HasStatusProtocol(Protocol):
    """Type checks if the charm uses advanced statuses."""

    status: StatusHandler


class CharmWithReconcile(ops.CharmBase, HasReconcileProtocol):
    """Merges ops class with protocol."""

    pass


class CharmWithStatus(ops.CharmBase, HasReconcileProtocol, HasStatusProtocol):
    """Merges ops class with protocol."""

    pass
