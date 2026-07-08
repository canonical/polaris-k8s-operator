# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from platform import machine

import jubilant
import pytest
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def platform() -> str:
    """Fixture to provide the platform architecture for testing."""
    platforms = {
        "x86_64": "amd64",
        "aarch64": "arm64",
    }
    return platforms.get(machine(), "amd64")


@pytest.fixture(scope="module")
def polaris_charm(platform: str) -> Path:
    """Path to the packed polaris charm."""
    if not (path := next(iter(Path.cwd().glob(f"*-{platform}.charm")), None)):
        raise FileNotFoundError("Could not find packed polaris charm.")

    return path


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest, platform: str) -> Generator[jubilant.Juju, None, None]:
    keep_models = bool(request.config.getoption("--keep-models"))
    model = request.config.getoption("--model")

    if model is None:
        with jubilant.temp_model(keep=keep_models) as juju:
            juju.wait_timeout = 10 * 60
            juju.model_config({"update-status-hook-interval": "60s"})
            juju.model_constraints({"arch": platform})

            yield juju  # run the test

            if request.session.testsfailed:
                log = juju.debug_log(limit=30)
                print(log, end="")
    else:
        juju = jubilant.Juju()
        juju.model = model
        try:
            juju.status()
        except jubilant.CLIError:
            juju.add_model(model)

        juju.wait_timeout = 10 * 60
        juju.model_config({"update-status-hook-interval": "60s"})
        juju.model_constraints({"arch": platform})

        yield juju  # run the test

        if not keep_models:
            juju.destroy_model(model, destroy_storage=True, force=True)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--keep-models",
        action="store_true",
        default=False,
        help="keep temporarily-created models",
    )
    parser.addoption(
        "--model",
        action="store",
        help="Juju model to use; if not provided, a new temporary model "
        "will be created for each test module",
    )
