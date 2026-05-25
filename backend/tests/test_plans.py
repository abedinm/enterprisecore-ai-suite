"""Plan / SKU feature gating."""
from __future__ import annotations

import pytest

from app.core import plans as plans_mod
from app.core.license_key import LicenseStatus, make_demo_key
from app.core.plans import Plan, has_feature, enabled_features, resolve_plan


def _stub_license(monkeypatch, *, plan: str | None = None, state: str = "active"):
    """Replace verify_license with a stub that returns the requested plan/state."""
    stub = LicenseStatus(
        valid=(state == "active"),
        state=state,
        reason="stub",
        customer="acme",
        plan=plan,
    )
    monkeypatch.setattr(
        "app.core.license_key.verify_license",
        lambda: stub,
    )


def test_no_license_resolves_to_evaluation(monkeypatch):
    _stub_license(monkeypatch, plan=None, state="evaluation")
    assert resolve_plan() is Plan.EVALUATION


def test_legacy_standard_plan_maps_to_core(monkeypatch):
    _stub_license(monkeypatch, plan="standard")
    assert resolve_plan() is Plan.CORE


def test_unknown_plan_downgrades_to_evaluation(monkeypatch):
    _stub_license(monkeypatch, plan="enterprise-platinum-unicorn")
    assert resolve_plan() is Plan.EVALUATION


def test_expired_license_downgrades_to_evaluation(monkeypatch):
    _stub_license(monkeypatch, plan="edu", state="expired")
    assert resolve_plan() is Plan.EVALUATION


def test_invalid_license_downgrades_to_evaluation(monkeypatch):
    _stub_license(monkeypatch, plan="edu", state="invalid")
    assert resolve_plan() is Plan.EVALUATION


def test_evaluation_unlocks_webchat_and_marketing(monkeypatch):
    _stub_license(monkeypatch, plan=None, state="evaluation")
    assert has_feature("webchat")
    assert has_feature("marketing")
    assert has_feature("marketing_templates")
    assert not has_feature("academic")


def test_core_unlocks_webchat_and_marketing_but_not_academic(monkeypatch):
    _stub_license(monkeypatch, plan="core")
    assert has_feature("webchat")
    assert has_feature("marketing")
    assert not has_feature("academic")


def test_edu_plan_unlocks_academic(monkeypatch):
    _stub_license(monkeypatch, plan="edu")
    assert has_feature("academic")
    assert has_feature("webchat")
    assert has_feature("marketing")


def test_verticals_plan_does_not_include_academic(monkeypatch):
    _stub_license(monkeypatch, plan="verticals")
    assert not has_feature("academic")
    assert has_feature("webchat")


def test_enabled_features_returns_set(monkeypatch):
    _stub_license(monkeypatch, plan="edu")
    feats = enabled_features()
    assert isinstance(feats, set)
    assert "academic" in feats
    assert "webchat" in feats


def test_unknown_feature_is_never_granted(monkeypatch):
    _stub_license(monkeypatch, plan="edu")
    assert not has_feature("quantum-blockchain-meta")


def test_signed_demo_key_resolves(monkeypatch):
    """End-to-end: a signed demo key with plan='edu' actually unlocks academic."""
    key = make_demo_key("test-customer", plan="edu")
    monkeypatch.setattr("app.core.config.settings.license_key", key)
    # resolve_plan reads via verify_license which reads settings.license_key
    assert resolve_plan() is Plan.EDU
    assert has_feature("academic")
