"""Tests for backend i18n: catalog loading, Accept-Language parsing,
fallback chain, and end-to-end localized error responses.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.i18n import (
    DEFAULT_LOCALE,
    RTL_LOCALES,
    SUPPORTED_LOCALES,
    parse_accept_language,
    translate,
)


# ---------------------------------------------------------------------------
# Unit tests — pure functions, no DB / no client.
# ---------------------------------------------------------------------------
def test_supported_locales_includes_eleven():
    """Frontend ships 11 locales; backend must mirror them so error strings
    don't degrade silently to English for paying customers."""
    assert len(SUPPORTED_LOCALES) == 11
    for code in ("en", "es", "fr", "de", "pt", "it", "ja", "zh", "ar", "he", "ur"):
        assert code in SUPPORTED_LOCALES


def test_rtl_locales_are_correct():
    assert RTL_LOCALES == {"ar", "he", "ur"}


def test_parse_accept_language_simple():
    assert parse_accept_language("fr") == "fr"
    assert parse_accept_language("de-DE") == "de"
    assert parse_accept_language("zh-CN") == "zh"


def test_parse_accept_language_quality_factors():
    """Higher-q tag wins; the first listed tag should NOT auto-win."""
    assert parse_accept_language("en;q=0.5, fr;q=0.9, de;q=0.3") == "fr"


def test_parse_accept_language_skips_unsupported():
    assert parse_accept_language("xx-YY,sw;q=0.9") == DEFAULT_LOCALE


def test_parse_accept_language_empty_falls_back():
    assert parse_accept_language(None) == "en"
    assert parse_accept_language("") == "en"


def test_translate_returns_english_when_locale_unknown():
    """`xx` isn't in the catalog → fall through to English."""
    assert translate("errors.invalid_credentials", "xx") == "Invalid email or password"


def test_translate_returns_key_when_truly_missing():
    """If neither the locale nor English has the key, surface it unchanged
    so logs / clients still get a non-empty string."""
    assert translate("not.a.real.key", "fr") == "not.a.real.key"


def test_translate_interpolates_placeholders():
    msg = translate("errors.not_found", "en", entity="User")
    assert msg == "User not found"
    # Spanish has the same placeholder
    msg_es = translate("errors.not_found", "es", entity="Usuario")
    assert msg_es == "Usuario no encontrado"


def test_translate_missing_placeholder_does_not_crash():
    """A `{foo}` reference with no kwarg should leave the placeholder intact
    rather than raising — the alternative is a 500 deep inside an error path."""
    msg = translate("errors.required_field", "en")  # no field= passed
    assert "{field}" in msg


def test_translate_handles_all_eleven_locales():
    """Sanity: every locale has the login-failure string. If a future
    catalog drops it we'd silently regress non-English users to 'errors.invalid_credentials'."""
    for code in SUPPORTED_LOCALES:
        msg = translate("errors.invalid_credentials", code)
        assert msg != "errors.invalid_credentials", f"missing in {code}"


# ---------------------------------------------------------------------------
# End-to-end — Accept-Language reaches the auth endpoint and shapes the
# error message in the response body.
# ---------------------------------------------------------------------------
def test_login_failure_localizes_via_accept_language(client: TestClient):
    """A French Accept-Language header should produce the French error string
    on a wrong-password login. The error `code` stays in English."""
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "wrong-password"},
        headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5"},
    )
    assert r.status_code == 401
    body = r.json()
    assert body["detail"] == "E-mail ou mot de passe invalides"
    # Code stays language-neutral for client-side branching.
    assert body["code"] == "authentication_error"


def test_login_failure_localizes_spanish(client: TestClient):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "nope"},
        headers={"Accept-Language": "es"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Correo o contraseña inválidos"


def test_login_failure_defaults_to_english(client: TestClient):
    """Missing or unsupported header → English."""
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "wrong"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"

    r2 = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "wrong"},
        headers={"Accept-Language": "xx-YY"},
    )
    assert r2.status_code == 401
    assert r2.json()["detail"] == "Invalid email or password"
