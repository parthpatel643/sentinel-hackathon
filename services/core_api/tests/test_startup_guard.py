"""The API must not come up on a shared network with the secrets published
in this repository."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from core_api import app as app_module
from sentinel_core.config import Settings


def test_non_local_environment_refuses_dev_default_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "get_settings", lambda: Settings(environment="prod"))

    with pytest.raises(RuntimeError, match="SENTINEL_JWT_SECRET"):
        app_module.create_app()


def test_non_local_environment_starts_once_secrets_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = SecretStr("x" * 32)
    settings = Settings(
        environment="prod",
        jwt_secret=secret,
        edge_service_token=secret,
        mtls_gateway_shared_secret=secret,
        media_url_signing_secret=secret,
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    assert app_module.create_app() is not None


def test_local_environment_keeps_the_zero_config_quickstart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "get_settings", lambda: Settings(environment="local"))

    assert app_module.create_app() is not None
