"""Frozen-friendly entry point. The PyInstaller bundle runs this script directly.

Reads BACKEND_PORT from env (defaults to 8765), listens on 127.0.0.1.
"""
from __future__ import annotations

import os
import sys

import uvicorn


def main() -> int:
    # Frozen builds run in a production-style environment: log aggregators
    # want one JSON object per line. The caller can still override by setting
    # LOG_FORMAT=human before launch.
    os.environ.setdefault("LOG_FORMAT", "json")

    port = int(os.environ.get("BACKEND_PORT", "8765"))
    host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level=os.environ.get("LOG_LEVEL", "info"),
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
