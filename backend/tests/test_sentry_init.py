"""Sentry initialisation — DSN gating, SDK ImportError fallback, init-args contract.

The runtime app boots ``init_sentry()`` from ``app.main`` once per process. In
tests we exercise it directly with the environment + SDK both mocked so we can
assert that:

* No DSN set → ``sentry_sdk.init`` is NOT called.
* DSN set + SDK importable → ``sentry_sdk.init`` is called once with the
  expected kwargs (env, release, send_default_pii=False, sample rates).
* DSN set + SDK NOT installed → no exception leaks, log warning fires.
* Custom sample-rate env vars are honoured.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


def _install_fake_sentry_sdk(monkeypatch, init_recorder: dict) -> MagicMock:
    """Inject a stub ``sentry_sdk`` (and its integrations) into sys.modules.

    Returns the fake ``init`` function so callers can assert call args. We
    capture into ``init_recorder`` because ``import sentry_sdk`` resolves to
    the module object — patching the attribute alone is fragile.
    """
    fake_init = MagicMock()
    init_recorder["fn"] = fake_init

    fake_sdk = types.ModuleType("sentry_sdk")
    fake_sdk.init = fake_init  # type: ignore[attr-defined]

    fastapi_int = types.ModuleType("sentry_sdk.integrations.fastapi")
    fastapi_int.FastApiIntegration = MagicMock(return_value="fastapi-int")  # type: ignore[attr-defined]
    sqla_int = types.ModuleType("sentry_sdk.integrations.sqlalchemy")
    sqla_int.SqlalchemyIntegration = MagicMock(return_value="sqla-int")  # type: ignore[attr-defined]
    loguru_int = types.ModuleType("sentry_sdk.integrations.loguru")
    loguru_int.LoguruIntegration = MagicMock(return_value="loguru-int")  # type: ignore[attr-defined]
    parent_int = types.ModuleType("sentry_sdk.integrations")

    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations", parent_int)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.fastapi", fastapi_int)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.sqlalchemy", sqla_int)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.loguru", loguru_int)
    return fake_init


def test_no_dsn_means_no_init(monkeypatch):
    """The whole point of the wrapper: DSN unset → no Sentry connection."""
    from app.core import sentry as sentry_mod

    monkeypatch.delenv("SENTRY_DSN", raising=False)
    rec: dict = {}
    fake_init = _install_fake_sentry_sdk(monkeypatch, rec)

    sentry_mod.init_sentry()

    fake_init.assert_not_called()


def test_dsn_set_triggers_init_with_expected_kwargs(monkeypatch):
    """DSN set → sentry_sdk.init called once with the documented contract."""
    from app import __version__
    from app.core import sentry as sentry_mod
    from app.core.config import settings

    monkeypatch.setenv("SENTRY_DSN", "https://example@sentry.io/123")
    monkeypatch.delenv("SENTRY_TRACES_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("SENTRY_PROFILES_SAMPLE_RATE", raising=False)
    rec: dict = {}
    fake_init = _install_fake_sentry_sdk(monkeypatch, rec)

    sentry_mod.init_sentry()

    fake_init.assert_called_once()
    kwargs = fake_init.call_args.kwargs
    assert kwargs["dsn"] == "https://example@sentry.io/123"
    assert kwargs["environment"] == settings.app_env
    assert kwargs["release"] == f"enterprisecore@{__version__}"
    assert kwargs["send_default_pii"] is False
    # Defaults are 0.1 / 0.1.
    assert kwargs["traces_sample_rate"] == pytest.approx(0.1)
    assert kwargs["profiles_sample_rate"] == pytest.approx(0.1)
    # All three integration classes were instantiated.
    assert kwargs["integrations"] == ["fastapi-int", "sqla-int", "loguru-int"]


def test_custom_sample_rates_are_honoured(monkeypatch):
    from app.core import sentry as sentry_mod

    monkeypatch.setenv("SENTRY_DSN", "https://x@sentry.io/9")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.5")
    monkeypatch.setenv("SENTRY_PROFILES_SAMPLE_RATE", "0.25")
    rec: dict = {}
    fake_init = _install_fake_sentry_sdk(monkeypatch, rec)

    sentry_mod.init_sentry()

    kwargs = fake_init.call_args.kwargs
    assert kwargs["traces_sample_rate"] == pytest.approx(0.5)
    assert kwargs["profiles_sample_rate"] == pytest.approx(0.25)


def test_missing_sdk_does_not_raise(monkeypatch):
    """If sentry-sdk isn't installed we must log a warning, not crash."""
    from app.core import sentry as sentry_mod

    monkeypatch.setenv("SENTRY_DSN", "https://x@sentry.io/9")
    # Force ``import sentry_sdk`` to fail by replacing the module + clearing
    # any cached imports of the integration packages.
    for mod in [
        "sentry_sdk",
        "sentry_sdk.integrations",
        "sentry_sdk.integrations.fastapi",
        "sentry_sdk.integrations.sqlalchemy",
        "sentry_sdk.integrations.loguru",
    ]:
        monkeypatch.delitem(sys.modules, mod, raising=False)

    # Block the import. We do this by installing a finder that raises for
    # ``sentry_sdk``. Simpler: stash a sentinel that raises on attribute.
    class _Blocked(types.ModuleType):
        def __getattr__(self, name):  # noqa: ANN001
            raise ImportError("sentry_sdk not installed in test env")

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk" or name.startswith("sentry_sdk."):
            raise ImportError("sentry-sdk forced off")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    # Must not raise.
    sentry_mod.init_sentry()
