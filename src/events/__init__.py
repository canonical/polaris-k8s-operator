# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from typing import TYPE_CHECKING

from ops import Object

from core.context import Context
from core.logging import WithLogging
from core.workload.polaris import PolarisWorkload

if TYPE_CHECKING:
    from charm import PolarisK8sCharm


class BaseEventHandler(Object, WithLogging):
    """Base class for all Event Handler classes in the Spark Integration Hub."""

    charm: PolarisK8sCharm
    context: Context
    polaris_workload: PolarisWorkload
    # TODO(console): Add console workload attr
