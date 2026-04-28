"""
dashboard/payments_tenant/gateways/registry.py
==============================================
Gateway registry — maps provider slug → concrete BaseGateway instance.

Usage
-----
    from dashboard.payments_tenant.gateways.registry import gateway_registry

    gw = gateway_registry.get("paystack")
    result = gw.initialize_payment(intent=intent, gateway_mode=gm, split_params={})

The registry is populated at module-import time by the gateways package
``__init__.py``.  Additional gateways can be registered at any point with::

    gateway_registry.register("my_gw", MyGateway())
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseGateway

logger = logging.getLogger("payments.gateway_registry")


class GatewayRegistry:
    """
    Thread-safe (reads only after app startup) registry of BaseGateway instances.

    Instances are singletons — one per provider slug — because concrete gateways
    hold no per-request state; all call-specific data is passed as arguments.
    """

    def __init__(self) -> None:
        self._registry: dict[str, "BaseGateway"] = {}

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, provider: str, gateway: "BaseGateway") -> None:
        """Register a gateway instance under a provider slug (e.g. "paystack")."""
        if provider in self._registry:
            logger.debug("Gateway registry: overwriting existing entry for '%s'.", provider)
        self._registry[provider] = gateway
        logger.debug("Gateway registry: registered '%s' → %s.", provider, type(gateway).__name__)

    # ── Lookup ───────────────────────────────────────────────────────────────

    def get(self, provider: str) -> "BaseGateway":
        """
        Return the gateway instance for *provider*.

        Raises ValueError if the provider is not registered so callers can fail
        fast rather than silently returning None.
        """
        gw = self._registry.get(provider)
        if gw is None:
            available = ", ".join(sorted(self._registry)) or "(none)"
            raise ValueError(
                f"No gateway registered for provider '{provider}'. "
                f"Available providers: {available}."
            )
        return gw

    def has(self, provider: str) -> bool:
        """Return True if a gateway is registered for *provider*."""
        return provider in self._registry

    def all_providers(self) -> list[str]:
        """Return a sorted list of registered provider slugs."""
        return sorted(self._registry)

    def __repr__(self) -> str:
        return f"GatewayRegistry({self.all_providers()})"


# Module-level singleton used across the payments subsystem.
gateway_registry = GatewayRegistry()
