"""Deeper unit coverage of workflow_engine internals.

These poke the small pure helpers (_resolve_dotted, _compare, _filter_matches,
_render_template, _render_config, _trigger_matches) and exercise more of the
action dispatch table without touching real Slack/Google/Email. The tests in
test_workflows.py already cover the bus-driven happy path.
"""
from __future__ import annotations

from types import SimpleNamespace


# ---------------------------------------------------------------------------
# _resolve_dotted
# ---------------------------------------------------------------------------
def test_resolve_dotted_walks_nested_dicts():
    from app.services.workflow_engine import _resolve_dotted

    payload = {"a": {"b": {"c": 42}}}
    assert _resolve_dotted(payload, "a.b.c") == 42


def test_resolve_dotted_missing_segment_returns_none():
    from app.services.workflow_engine import _resolve_dotted

    assert _resolve_dotted({"a": 1}, "a.b") is None
    assert _resolve_dotted({}, "x") is None


def test_resolve_dotted_against_non_dict_value():
    from app.services.workflow_engine import _resolve_dotted

    # 'a' is a list; the walk should bail because list != dict in this DSL.
    assert _resolve_dotted({"a": [1, 2, 3]}, "a.0") is None


# ---------------------------------------------------------------------------
# _compare
# ---------------------------------------------------------------------------
def test_compare_numeric_operators():
    from app.services.workflow_engine import _compare

    assert _compare(100, "> 50") is True
    assert _compare(100, ">= 100") is True
    assert _compare(100, "< 50") is False
    assert _compare(100, "<= 99") is False
    assert _compare(50, "!= 49") is True


def test_compare_string_equality_default():
    from app.services.workflow_engine import _compare

    assert _compare("hello", "hello") is True
    assert _compare("hello", "world") is False


def test_compare_in_membership():
    from app.services.workflow_engine import _compare

    assert _compare("eu", "in:eu,us,apac") is True
    assert _compare("antarctica", "in:eu,us,apac") is False


def test_compare_raw_value_equality():
    from app.services.workflow_engine import _compare

    # Non-string op_spec means literal equality.
    assert _compare(42, 42) is True
    assert _compare("x", "y") is False


def test_compare_inequality_falls_back_to_string():
    """!= with non-numeric actual should fall through to string compare."""
    from app.services.workflow_engine import _compare

    assert _compare("apple", "!= banana") is True
    assert _compare("apple", "!= apple") is False


def test_compare_numeric_op_on_non_numeric_returns_false():
    from app.services.workflow_engine import _compare

    assert _compare("not-a-number", "> 10") is False


# ---------------------------------------------------------------------------
# _filter_matches
# ---------------------------------------------------------------------------
def test_filter_matches_empty_filter_always_true():
    from app.services.workflow_engine import _filter_matches

    assert _filter_matches({"anything": 1}, {}) is True
    assert _filter_matches({}, {}) is True


def test_filter_matches_all_clauses_must_pass():
    from app.services.workflow_engine import _filter_matches

    payload = {"amount": 1000, "region": "eu"}
    assert _filter_matches(payload, {"amount": "> 500", "region": "eu"}) is True
    assert _filter_matches(payload, {"amount": "> 500", "region": "apac"}) is False


def test_filter_matches_dotted_paths():
    from app.services.workflow_engine import _filter_matches

    payload = {"customer": {"plan": "growth"}}
    assert _filter_matches(payload, {"customer.plan": "growth"}) is True
    assert _filter_matches(payload, {"customer.plan": "starter"}) is False


# ---------------------------------------------------------------------------
# _render_template / _render_config
# ---------------------------------------------------------------------------
def test_render_template_skips_strings_without_jinja_markers():
    from app.services.workflow_engine import _render_template

    assert _render_template("plain text", {"x": 1}) == "plain text"


def test_render_template_substitutes_payload_keys():
    from app.services.workflow_engine import _render_template

    out = _render_template("Hello {{ name }}!", {"name": "World"})
    assert out == "Hello World!"


def test_render_template_non_string_passthrough():
    from app.services.workflow_engine import _render_template

    assert _render_template(123, {}) == 123
    assert _render_template(None, {}) is None
    assert _render_template([1, 2], {}) == [1, 2]


def test_render_template_swallows_jinja_errors():
    """Bad templates must not blow up the workflow — they fall back to raw."""
    from app.services.workflow_engine import _render_template

    # Unclosed expression. Jinja raises; we eat it and return the original.
    out = _render_template("Hello {{ name", {"name": "x"})
    assert out == "Hello {{ name"


def test_render_config_recurses_into_nested_dicts_and_lists():
    from app.services.workflow_engine import _render_config

    cfg = {
        "title": "Lead {{ name }}",
        "body": {"deep": "from {{ source }}"},
        "tags": ["{{ tag1 }}", "{{ tag2 }}"],
        "count": 5,
    }
    out = _render_config(
        cfg,
        {"name": "Acme", "source": "google", "tag1": "vip", "tag2": "hot"},
    )
    assert out["title"] == "Lead Acme"
    assert out["body"]["deep"] == "from google"
    assert out["tags"] == ["vip", "hot"]
    assert out["count"] == 5


# ---------------------------------------------------------------------------
# _trigger_matches
# ---------------------------------------------------------------------------
def test_trigger_matches_wildcard_event_type():
    from app.services.workflow_engine import _trigger_matches

    wf = SimpleNamespace(trigger_event_type="crm.*", trigger_filter={})
    event = SimpleNamespace(type="crm.lead.created", payload={})
    assert _trigger_matches(wf, event) is True

    other_event = SimpleNamespace(type="hr.employee.created", payload={})
    assert _trigger_matches(wf, other_event) is False


def test_trigger_matches_star_matches_anything():
    from app.services.workflow_engine import _trigger_matches

    wf = SimpleNamespace(trigger_event_type="*", trigger_filter={})
    event = SimpleNamespace(type="any.event.at.all", payload={})
    assert _trigger_matches(wf, event) is True


def test_trigger_matches_combines_pattern_and_filter():
    from app.services.workflow_engine import _trigger_matches

    wf = SimpleNamespace(
        trigger_event_type="crm.deal.won",
        trigger_filter={"amount": "> 1000"},
    )
    ok = SimpleNamespace(type="crm.deal.won", payload={"amount": 5000})
    bad = SimpleNamespace(type="crm.deal.won", payload={"amount": 100})
    assert _trigger_matches(wf, ok) is True
    assert _trigger_matches(wf, bad) is False


# ---------------------------------------------------------------------------
# Action dispatch — exercise unhappy branches that don't need network IO.
# ---------------------------------------------------------------------------
def test_action_update_field_is_not_implemented():
    from app.services.workflow_engine import _action_update_field

    result = _action_update_field({"model": "x", "record_id": "y", "field": "z", "value": "v"},
                                  SimpleNamespace(payload={}, tenant_id=None, type="x"), None)
    assert result["ok"] is False
    assert "not implemented" in result["error"]


def test_action_post_webhook_rejects_missing_url():
    from app.services.workflow_engine import _action_post_webhook

    result = _action_post_webhook({}, SimpleNamespace(payload={}, tenant_id=None, type="x"), None)
    assert result["ok"] is False
    assert "url" in result["error"]


def test_action_send_email_rejects_missing_recipient():
    from app.services.workflow_engine import _action_send_email

    result = _action_send_email({"subject": "x"}, SimpleNamespace(payload={}, tenant_id=None, type="x"), None)
    assert result["ok"] is False


def test_action_types_catalog_is_well_formed():
    """Every entry in ACTION_TYPES has the keys the UI expects."""
    from app.services.workflow_engine import ACTION_TYPES

    for entry in ACTION_TYPES:
        assert "type" in entry
        assert "description" in entry
        assert "config_schema" in entry
        assert isinstance(entry["config_schema"], dict)
