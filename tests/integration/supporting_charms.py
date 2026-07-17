# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Supporting charms for integration tests."""

from dataclasses import dataclass, fields
from typing import TypedDict


@dataclass
class SingleVariantCharmVersion:
    """A supporting charm variant."""

    charm: str
    channel: str
    app: str
    base: str | None = None
    revision: int | None = None
    num_units: int = 1
    trust: bool = False

    def to_dict(self) -> dict:
        """Convert to ready-to-deploy arguments.

        Compared to dataclasses.asdict(), we exclude None values.
        """
        out_dict = {}
        for field in fields(self):
            if (value := getattr(self, field.name)) is not None:
                out_dict[field.name] = value
        return out_dict


class CharmVersion(TypedDict):  # Note: add total=False if needed (e.g. no arm64)
    """A supporting charm to deploy for the polaris-k8s-operator integration tests."""

    amd64: SingleVariantCharmVersion
    arm64: SingleVariantCharmVersion


Metastore: CharmVersion = {
    "amd64": SingleVariantCharmVersion(
        charm="postgresql-k8s", channel="16/stable", app="metastore", trust=True
    ),
    "arm64": SingleVariantCharmVersion(
        charm="postgresql-k8s", channel="16/stable", app="metastore", trust=True
    ),
}

S3: CharmVersion = {
    "amd64": SingleVariantCharmVersion(charm="s3-integrator", channel="2/stable", app="s3"),
    "arm64": SingleVariantCharmVersion(charm="s3-integrator", channel="2/stable", app="s3"),
}
