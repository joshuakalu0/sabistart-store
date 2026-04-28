"""
dashboard/payments_tenant/gateways/stripe.py
============================================
Stripe concrete gateway implementation.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

from .base import BaseGateway, GatewayInitResult, GatewayVerifyResult

logger = logging.getLogger("payments.gateway.stripe")

# Maximum age (seconds) of a Stripe webhook timestamp before we reject it.
_STRIPE_TIMESTAMP_TOLERANCE = 300


class StripeGateway(BaseGateway):
    """Stripe-specific gateway adapter."""

    provider = "stripe"

    # ── initialize ──────────────────────────────────────────────────────────

    def initialize_payment(self, *, intent, gateway_mode, split_params: dict) -> GatewayInitResult:
        from dashboard.payments_tenant.services.provider_checkout import _initialize_stripe

        result = _initialize_stripe(intent, gateway_mode, split_params)
        return GatewayInitResult(
            success=result.success,
            provider=self.provider,
            reference=result.reference,
            authorization_url=result.authorization_url,
            access_code=result.access_code,
            client_secret=result.client_secret,
            gateway_intent_id=result.gateway_intent_id,
            public_key=result.public_key,
            is_redirect=result.is_redirect,
            raw_response=result.raw_response,
            error=result.error,
        )

    # ── verify ───────────────────────────────────────────────────────────────

    def verify_payment(self, *, intent, payload: dict, headers: dict | None = None) -> GatewayVerifyResult:
        from dashboard.payments_tenant.services.provider_checkout import _verify_stripe

        result = _verify_stripe(intent, payload)
        return GatewayVerifyResult(
            success=result.success,
            provider=self.provider,
            payment_status=result.payment_status,
            gateway_reference=result.gateway_reference,
            gateway_transaction_id=result.gateway_transaction_id,
            amount=result.amount,
            currency=result.currency,
            payment_channel=result.payment_channel,
            gateway_message=result.gateway_message,
            raw_response=result.raw_response,
            error=result.error,
        )

    # ── webhook signature ────────────────────────────────────────────────────

    def validate_webhook_signature(self, *, payload_bytes: bytes, signature: str, secret: str) -> bool:
        """
        Stripe signs webhooks with HMAC-SHA256.  The ``Stripe-Signature`` header
        contains a timestamp (``t=``) and one or more HMAC signatures (``v1=``).

        We reconstruct the signed payload as ``{timestamp}.{body}`` and verify
        against all v1 signatures.  We also enforce a timestamp tolerance window
        to prevent replay attacks.

        Reference: https://stripe.com/docs/webhooks/signatures
        """
        if not secret or not signature:
            logger.warning("Stripe webhook: missing secret or Stripe-Signature header.")
            return False

        try:
            parts = dict(item.split("=", 1) for item in signature.split(",") if "=" in item)
            timestamp_str = parts.get("t", "")
            v1_sigs = [v for k, v in parts.items() if k == "v1"]

            if not timestamp_str or not v1_sigs:
                logger.warning("Stripe webhook: malformed Stripe-Signature header.")
                return False

            timestamp = int(timestamp_str)
            now = int(time.time())
            if abs(now - timestamp) > _STRIPE_TIMESTAMP_TOLERANCE:
                logger.warning(
                    "Stripe webhook: timestamp %s is outside tolerance (%ss).",
                    timestamp,
                    _STRIPE_TIMESTAMP_TOLERANCE,
                )
                return False

            signed_payload = f"{timestamp}.".encode() + payload_bytes
            expected = hmac.new(
                secret.encode("utf-8"), signed_payload, hashlib.sha256
            ).hexdigest()

            return any(hmac.compare_digest(expected, sig) for sig in v1_sigs)

        except Exception:
            logger.exception("Stripe webhook signature validation error.")
            return False
