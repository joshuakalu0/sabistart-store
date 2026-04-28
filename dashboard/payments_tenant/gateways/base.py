"""
dashboard/payments_tenant/gateways/base.py
==========================================
Abstract Base Gateway interface.

Every concrete gateway implementation must subclass BaseGateway and
implement all three abstract methods.  The registry uses this type as its
common contract so callers never need to know which concrete class they hold.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class GatewayInitResult:
    """Result returned by BaseGateway.initialize_payment()."""
    success: bool
    provider: str = ""
    reference: str = ""                 # Our internal reference / tx_ref
    authorization_url: str = ""         # Hosted checkout redirect URL
    access_code: str = ""               # Paystack-specific access code
    client_secret: str = ""            # Stripe-specific client secret
    gateway_intent_id: str = ""         # Gateway's own identifier for this payment
    public_key: str = ""               # Frontend-safe public/publishable key
    is_redirect: bool = True            # False for manual/COD providers
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class GatewayVerifyResult:
    """Result returned by BaseGateway.verify_payment()."""
    success: bool
    provider: str = ""
    payment_status: str = ""            # "success" | "failed" | "pending" | …
    gateway_reference: str = ""
    gateway_transaction_id: str = ""
    amount: Decimal = Decimal("0.00")
    currency: str = ""
    payment_channel: str = ""
    gateway_message: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class BaseGateway(ABC):
    """
    Abstract interface every payment gateway adapter must satisfy.

    Usage
    -----
    All three methods are called with keyword arguments only to prevent
    positional-argument ambiguities across different concrete implementations.

    Lifecycle
    ---------
    1. initialize_payment  — called at checkout creation; returns a redirect URL.
    2. verify_payment      — called after the customer returns or on webhook receipt;
                             returns the definitive payment status.
    3. validate_webhook_signature — called before any webhook payload is trusted;
                             returns True only if the HMAC/signature is valid.
    """

    # Subclasses set this to their provider slug, e.g. "paystack"
    provider: str = ""

    @abstractmethod
    def initialize_payment(
        self,
        *,
        intent,
        gateway_mode,
        split_params: dict,
    ) -> GatewayInitResult:
        """
        Initialise a hosted payment session at the gateway.

        Parameters
        ----------
        intent      : PaymentIntent ORM instance
        gateway_mode: TenantGatewayMode ORM instance
        split_params: dict with subaccount / transaction_charge / bearer (PLATFORM mode)

        Returns GatewayInitResult.  On failure set success=False and populate error.
        """

    @abstractmethod
    def verify_payment(
        self,
        *,
        intent,
        payload: dict,
        headers: dict | None = None,
    ) -> GatewayVerifyResult:
        """
        Verify a payment using the gateway's verification API.

        Parameters
        ----------
        intent  : PaymentIntent ORM instance
        payload : Callback / webhook query-params dict
        headers : Raw HTTP headers (needed by some gateways for signature re-check)

        Returns GatewayVerifyResult.  payment_status should be one of
        "success", "failed", "pending", "processing".
        """

    @abstractmethod
    def validate_webhook_signature(
        self,
        *,
        payload_bytes: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """
        Verify the HMAC / shared-secret signature on an incoming webhook.

        Parameters
        ----------
        payload_bytes : Raw bytes of the HTTP request body
        signature     : Value from the gateway's signature header
        secret        : Webhook secret key retrieved from the credential store

        Returns True only when the signature is cryptographically valid.
        NEVER log ``secret`` — treat it as a password.
        """
