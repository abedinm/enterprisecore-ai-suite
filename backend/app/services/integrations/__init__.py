"""Third-party integration framework.

Each integration is a concrete subclass of :class:`Integration` registered
in :mod:`registry`. The registry is the only entry point endpoint code
should use to look up a connector by key — direct imports are avoided so
optional connectors (those requiring uninstalled libraries) can fail
quietly without breaking the catalog endpoint.
"""
from app.services.integrations.base import Integration  # noqa: F401
from app.services.integrations.registry import (  # noqa: F401
    get_integration, list_integrations, register_all_subscribers,
)
