"""ETag + If-None-Match helpers for cheap list-endpoint caching.

The "list invoices", "list customers", "list employees" endpoints are the
hottest reads in the system. Each one re-serialises the same JSON for
every page navigation even when the underlying data hasn't changed.

ETag short-circuits that:

    @router.get("/customers")
    def list_customers(request: Request, db: ... = ..., ...):
        rows = db.scalars(...).all()
        return etag_response(request, rows, key_fields=("id", "updated_at"))

If the client sends ``If-None-Match: "<previous etag>"`` and we hash to
the same value, we return ``304 Not Modified`` with no body. The browser
keeps using its cached copy — round trip drops from ~120ms to ~5ms and
the JSON serialiser never runs.

Cache key inputs
----------------

The hash is computed from a tuple of ``(id, updated_at)`` per row (or any
fields the caller picks). We don't hash the full JSON because:

  1. updated_at is usually enough — invariant to representation tweaks.
  2. Hashing 1000 rows of small tuples is ~50µs; hashing the JSON is
     500µs and grows with payload size.
  3. The ETag is stable across schema-version bumps because we only
     hash the columns the caller declares.

Weak vs strong ETags
--------------------

We emit STRONG ETags (no ``W/`` prefix) because byte-identical responses
are byte-identical to the client. Strong ETags work with `Range` requests
too, even though FastAPI doesn't currently expose any.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Sequence

from fastapi import Request, Response
from starlette.responses import JSONResponse


def compute_etag(rows: Iterable[Any], *, key_fields: Sequence[str] = ("id", "updated_at")) -> str:
    """Hash *rows* down to a stable strong ETag.

    Accepts ORM instances, dicts, or Pydantic models — whatever exposes the
    named attributes via ``getattr`` or ``.get``.
    """
    h = hashlib.blake2b(digest_size=16)
    h.update(b"|".join(f.encode() for f in key_fields))
    for row in rows:
        for f in key_fields:
            v = getattr(row, f, None)
            if v is None and isinstance(row, dict):
                v = row.get(f)
            if v is None:
                continue
            h.update(b"|")
            # str() handles dates, UUIDs, Decimals, ints in one go.
            h.update(str(v).encode("utf-8"))
        h.update(b"\n")
    return '"' + h.hexdigest() + '"'


def etag_short_circuit(request: Request, etag: str) -> Response | None:
    """Return a 304 Response if the request matches *etag*, else None.

    Callers should:

        et = compute_etag(rows)
        if (resp := etag_short_circuit(request, et)) is not None:
            return resp
        return JSONResponse([row.dict() for row in rows], headers={"ETag": et})
    """
    inm = request.headers.get("if-none-match", "")
    if inm and any(_eq_etag(token, etag) for token in (t.strip() for t in inm.split(","))):
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"})
    return None


def _eq_etag(a: str, b: str) -> bool:
    """Compare two ETag tokens, ignoring optional weak ``W/`` prefix."""
    if not a or not b:
        return False
    aa = a[2:] if a.startswith("W/") else a
    bb = b[2:] if b.startswith("W/") else b
    return aa == bb


def etag_response(
    request: Request,
    rows: Sequence[Any],
    *,
    key_fields: Sequence[str] = ("id", "updated_at"),
    serialise: callable = None,  # type: ignore[assignment]
) -> Response:
    """One-call helper: build the ETag, short-circuit on a match, otherwise
    serialise the rows and emit the ETag header.

    ``serialise`` defaults to ``[r.__dict__ for r in rows]`` (raw ORM
    columns minus SQLAlchemy internals). For Pydantic schemas pass
    ``serialise=lambda rs: [Schema.model_validate(r).model_dump() for r in rs]``.
    """
    etag = compute_etag(rows, key_fields=key_fields)
    cached = etag_short_circuit(request, etag)
    if cached is not None:
        return cached
    if serialise is None:
        def serialise(rs):
            out = []
            for r in rs:
                if hasattr(r, "__dict__"):
                    out.append({k: v for k, v in r.__dict__.items() if not k.startswith("_")})
                else:
                    out.append(r)
            return out
    body = serialise(rows)
    return JSONResponse(
        content=json.loads(json.dumps(body, default=str)),
        headers={"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"},
    )
