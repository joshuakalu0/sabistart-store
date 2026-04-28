"""
dashboard/payments_tenant/gateways/__init__.py
=============================================
Gateways package.

Importing this package registers all built-in gateway implementations into
the module-level ``gateway_registry`` singleton.  Any code that needs to
use a gateway should import from here:

    from dashboard.payments_tenant.gateways import gateway_registry
    from dashboard.payments_tenant.gateways.base import BaseGateway, GatewayInitResult, GatewayVerifyResult
"""
from .base import BaseGateway, GatewayInitResult, GatewayVerifyResult
from .registry import GatewayRegistry, gateway_registry
from .paystack import PaystackGateway
from .flutterwave import FlutterwaveGateway
from .stripe import StripeGateway

# ── Register all built-in gateways ──────────────────────────────────────────
gateway_registry.register("paystack",    PaystackGateway())
gateway_registry.register("flutterwave", FlutterwaveGateway())
gateway_registry.register("stripe",      StripeGateway())

__all__ = [
    "BaseGateway",
    "GatewayInitResult",
    "GatewayVerifyResult",
    "GatewayRegistry",
    "gateway_registry",
    "PaystackGateway",
    "FlutterwaveGateway",
    "StripeGateway",
]
