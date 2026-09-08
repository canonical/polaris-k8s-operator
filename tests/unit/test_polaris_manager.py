# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the Polaris manager."""

from unittest.mock import patch

from core.constants import REST_PORT
from managers.polaris import PolarisManager


def test_management_api_options_are_compatible_with_polaris_client() -> None:
    """The options namespace must define every attribute the Polaris client builder reads."""
    manager = PolarisManager(context=None, workload=None, is_leader=True)
    with patch("apache_polaris.cli.api_client_builder.ApiClient.call_api") as patched_call_api:
        patched_call_api.return_value.response.data = '{"access_token": "token"}'
        api = manager._api("some-password")

    assert api is not None
    assert api.api_client.configuration.host == f"http://localhost:{REST_PORT}/api/management/v1"
