"""Auto-numbering for Site Instructions (SI-NNN) and Variations (VAR-NNN)."""
from __future__ import annotations

from tests._construction_helpers import make_project, set_verticals_plan


API = "/api/v1/construction"


def test_si_numbers_increment_within_project(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers)
    nums = []
    for i in range(3):
        r = client.post(
            f"{API}/projects/{p['id']}/site-instructions",
            headers=auth_headers,
            json={"title": f"SI {i}"},
        )
        assert r.status_code == 201, r.text
        nums.append(r.json()["number"])
    assert nums == ["SI-001", "SI-002", "SI-003"]


def test_si_numbers_isolated_between_projects(client, auth_headers, monkeypatch):
    """Each construction project gets its own SI-001 counter."""
    set_verticals_plan(monkeypatch)
    p1 = make_project(client, auth_headers, name="Project Alpha")
    p2 = make_project(client, auth_headers, name="Project Beta")

    # Two on P1, one on P2 — both projects must start from SI-001.
    a = client.post(
        f"{API}/projects/{p1['id']}/site-instructions",
        headers=auth_headers, json={"title": "P1 first"},
    ).json()
    b = client.post(
        f"{API}/projects/{p1['id']}/site-instructions",
        headers=auth_headers, json={"title": "P1 second"},
    ).json()
    c = client.post(
        f"{API}/projects/{p2['id']}/site-instructions",
        headers=auth_headers, json={"title": "P2 first"},
    ).json()
    assert a["number"] == "SI-001"
    assert b["number"] == "SI-002"
    assert c["number"] == "SI-001"


def test_variation_numbers_increment_within_project(
    client, auth_headers, monkeypatch,
):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers)
    nums = []
    for i in range(4):
        r = client.post(
            f"{API}/projects/{p['id']}/variations",
            headers=auth_headers,
            json={"title": f"VAR {i}", "cost_impact": "100.00"},
        )
        assert r.status_code == 201, r.text
        nums.append(r.json()["number"])
    assert nums == ["VAR-001", "VAR-002", "VAR-003", "VAR-004"]


def test_si_number_helper_skips_double_digit_correctly(client, auth_headers, monkeypatch):
    """Make sure the helper sorts numerically, not lexicographically — SI-9
    must come before SI-10."""
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers)
    for _ in range(12):
        r = client.post(
            f"{API}/projects/{p['id']}/site-instructions",
            headers=auth_headers,
            json={"title": "x"},
        )
        assert r.status_code == 201, r.text
    last = client.get(
        f"{API}/projects/{p['id']}/site-instructions",
        headers=auth_headers,
    ).json()[0]
    # Most recent (descending order in list) should be SI-012.
    assert last["number"] == "SI-012"
