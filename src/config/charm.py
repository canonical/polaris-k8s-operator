# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Structured configuration for the Polaris charm."""

import re
from typing import Annotated, Any, Callable

from charms.data_platform_libs.v1.data_models import BaseConfigModel
from pydantic import Field, model_serializer

SECRET_REGEX = re.compile("secret:[a-z0-9]{20}")


class PolarisCharmConfig(BaseConfigModel):
    """Charm structured configuration."""

    storage_access_model: Annotated[str, Field(alias="storage-access-model")]
    sts_endpoint: Annotated[str, Field(alias="sts-endpoint")]
    system_user: Annotated[str | None, Field(alias="system-user", pattern=SECRET_REGEX)] = None

    @model_serializer(mode="wrap")
    def serialize_and_exclude(self, handler: Callable[["PolarisCharmConfig"], Any]) -> Any:
        """Exclude secrets."""
        data = handler(self)
        if isinstance(data, dict):
            data.pop("system_user", None)
        return data
