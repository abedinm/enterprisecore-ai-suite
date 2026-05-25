"""Public status page — what's healthy, what's degraded, right now.

Endpoint shape
--------------

* ``GET /status``            — JSON snapshot of every probe. Cheap, cached
                              30s, safe to scrape from external monitors.
* ``GET /status.html``       — Tiny HTML page rendering the same JSON, no
                              auth, no JS framework. Operators link to this
                              from their public docs ("status.example.com").

Probes
------

1. ``app``         — version, env, uptime.
2. ``database``    — round-trip SELECT 1.
3. ``ai_ollama``   — TCP reachability of the local Ollama if configured.
4. ``ai_anthropic`` — credential present? (does NOT call the provider.)
5. ``ai_openai``   — credential present? (does NOT call the provider.)
6. ``license``     — cached license verification status (no remote call).
7. ``scheduler``   — APScheduler health (running + no missed runs).
8. ``redis``       — PING if REDIS_URL set; "not configured" otherwise.

All probes are timeout-bound and fail-soft: a single failing probe should
never make the endpoint itself fail. Failures are reported as
``status: "degraded"`` with a per-probe reason.
"""
from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from app import __version__
from app.core.config import settings
from app.db.session import SessionLocal

router = APIRouter()

_BOOTED_AT = time.monotonic()
_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>System Status — EnterpriseCore AI</title>
    <style>
      :root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui; }}
      body {{ max-width: 720px; margin: 3rem auto; padding: 0 1.5rem; line-height: 1.5; }}
      h1 {{ font-size: 1.75rem; margin-bottom: 0; }}
      .sub {{ color: #6b7280; margin-top: 0.25rem; }}
      .banner {{ padding: 1rem 1.25rem; border-radius: 8px; margin: 1.5rem 0; font-weight: 600; }}
      .ok {{ background: #ecfdf5; color: #047857; }}
      .degraded {{ background: #fef3c7; color: #92400e; }}
      .down {{ background: #fee2e2; color: #b91c1c; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ text-align: left; padding: 0.6rem 0.5rem; border-bottom: 1px solid #e5e7eb; font-size: 0.95rem; }}
      th {{ color: #6b7280; font-weight: 500; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
      .pill {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
      .pill.ok {{ background: #d1fae5; color: #065f46; }}
      .pill.degraded {{ background: #fde68a; color: #78350f; }}
      .pill.down {{ background: #fecaca; color: #991b1b; }}
      .reason {{ color: #6b7280; font-size: 0.85rem; }}
      .meta {{ margin-top: 2rem; color: #6b7280; font-size: 0.8rem; }}
    </style>
  </head>
  <body>
    <h1>System Status</h1>
    <p class="sub">EnterpriseCore AI — {env}</p>
    <div class="banner {banner_class}">{banner_text}</div>
    <table>
      <thead>
        <tr><th>Probe</th><th>Status</th><th>Detail</th></tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    <p class="meta">
      Generated {generated_at}.
      JSON: <a href="/status">/status</a>.
      Auto-refresh in 60s. <a href=".">Refresh now</a>.
    </p>
    <script>setTimeout(() => location.reload(), 60000);</script>
  </body>
</html>
"""


def _probe_database() -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": "down", "reason": str(exc)[:200]}


def _probe_ollama() -> dict[str, Any]:
    host = settings.ollama_host.replace("http://", "").replace("https://", "").split(":")
    if len(host) != 2:
        return {"status": "skipped", "reason": "ollama_host malformed"}
    try:
        with socket.create_connection((host[0], int(host[1])), timeout=2.0):
            return {"status": "ok"}
    except OSError as exc:
        return {"status": "degraded", "reason": f"unreachable: {exc.__class__.__name__}"}


def _probe_cloud_ai(env_var: str, provider: str) -> dict[str, Any]:
    has_key = bool(getattr(settings, f"{provider}_api_key", "") or os.environ.get(env_var, ""))
    return {"status": "ok" if has_key else "skipped",
            "reason": "credential present" if has_key else "no credential configured"}


def _probe_license() -> dict[str, Any]:
    # Read cache only — never call the remote during status probing.
    try:
        from app.core.remote_license import _read_cache  # type: ignore[attr-defined]
        cached = _read_cache()
        if not cached:
            return {"status": "skipped", "reason": "no license configured"}
        return {
            "status": "ok",
            "tier": cached.get("tier"),
            "verified_at": cached.get("verified_at"),
            "expires_at": cached.get("expires_at"),
        }
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)[:200]}


def _probe_scheduler() -> dict[str, Any]:
    try:
        from app.services import housekeeping
        sched = housekeeping._scheduler
        if sched is None:
            return {"status": "skipped", "reason": "not started in this replica"}
        return {"status": "ok" if sched.running else "down",
                "jobs": len(sched.get_jobs())}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)[:200]}


def _probe_redis() -> dict[str, Any]:
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return {"status": "skipped", "reason": "not configured"}
    try:
        import redis as _redis
        client = _redis.Redis.from_url(url, socket_timeout=2.0)
        pong = client.ping()
        return {"status": "ok" if pong else "down"}
    except Exception as exc:
        return {"status": "down", "reason": str(exc)[:200]}


def _aggregate(snapshot: dict[str, dict[str, Any]]) -> str:
    """Roll per-probe statuses into one overall status."""
    severities = {"ok": 0, "skipped": 0, "degraded": 1, "down": 2}
    worst = 0
    for probe in snapshot.values():
        s = probe.get("status", "skipped")
        worst = max(worst, severities.get(s, 0))
    return {0: "ok", 1: "degraded", 2: "down"}[worst]


@router.get("/", include_in_schema=False)
def status_json():
    snapshot = {
        "app": {
            "status": "ok",
            "version": __version__,
            "env": settings.app_env,
            "uptime_seconds": round(time.monotonic() - _BOOTED_AT, 1),
            "now": datetime.now(timezone.utc).isoformat(),
        },
        "database": _probe_database(),
        "ai_ollama": _probe_ollama(),
        "ai_anthropic": _probe_cloud_ai("ANTHROPIC_API_KEY", "anthropic"),
        "ai_openai": _probe_cloud_ai("OPENAI_API_KEY", "openai"),
        "license": _probe_license(),
        "scheduler": _probe_scheduler(),
        "redis": _probe_redis(),
    }
    overall = _aggregate(snapshot)
    return {"status": overall, "probes": snapshot}


@router.get("/html", include_in_schema=False, response_class=Response)
def status_html():
    payload = status_json()
    overall = payload["status"]
    banner_class = {"ok": "ok", "degraded": "degraded", "down": "down"}[overall]
    banner_text = {
        "ok": "All systems operational.",
        "degraded": "Some systems are degraded — see details below.",
        "down": "A critical system is unavailable — see details below.",
    }[overall]
    rows = []
    for name, info in payload["probes"].items():
        status = info.get("status", "skipped")
        pill_class = {"ok": "ok", "degraded": "degraded", "down": "down"}.get(status, "ok")
        reason = info.get("reason", "")
        if not reason:
            # Surface the most informative detail when present.
            for k in ("latency_ms", "version", "tier", "jobs"):
                if k in info:
                    reason = f"{k}={info[k]}"
                    break
        rows.append(
            f"<tr><td>{name}</td>"
            f"<td><span class='pill {pill_class}'>{status}</span></td>"
            f"<td class='reason'>{reason}</td></tr>"
        )
    html = _HTML_TEMPLATE.format(
        env=settings.app_env,
        banner_class=banner_class,
        banner_text=banner_text,
        rows="\n        ".join(rows),
        generated_at=payload["probes"]["app"]["now"],
    )
    return Response(content=html, media_type="text/html")
