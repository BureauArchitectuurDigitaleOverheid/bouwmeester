"""Tests for the fail-closed authentication config validator (#320).

Without OIDC the AuthRequiredMiddleware is a no-op, so Settings must
refuse to construct unless DEV_NO_AUTH is explicitly opted into.

``_env_file=None`` keeps these from picking up a local .env, and every
relevant field is passed explicitly so the host environment (conftest
sets DEV_NO_AUTH=1 process-wide) cannot mask the behaviour.
"""

import pytest

from bouwmeester.core.config import Settings


def _make(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_no_oidc_and_no_dev_opt_in_refuses_to_start() -> None:
    with pytest.raises(ValueError, match="Authenticatie is niet geconfigureerd"):
        _make(OIDC_ISSUER="", DEV_NO_AUTH=False)


def test_dev_no_auth_opt_in_allows_start_without_oidc() -> None:
    settings = _make(OIDC_ISSUER="", DEV_NO_AUTH=True)
    assert settings.OIDC_ISSUER == ""
    assert settings.DEV_NO_AUTH is True


def test_explicit_oidc_issuer_allows_start() -> None:
    settings = _make(
        OIDC_ISSUER="https://idp.example/realms/bm",
        DEV_NO_AUTH=False,
        SESSION_SECRET_KEY="a-secure-random-value",
    )
    assert settings.OIDC_ISSUER == "https://idp.example/realms/bm"


def test_oidc_issuer_derived_from_zad_vars_satisfies_validator() -> None:
    settings = _make(
        OIDC_ISSUER="",
        OIDC_URL="https://idp.example",
        OIDC_REALM="bm",
        DEV_NO_AUTH=False,
        SESSION_SECRET_KEY="a-secure-random-value",
    )
    assert settings.OIDC_ISSUER == "https://idp.example/realms/bm"
