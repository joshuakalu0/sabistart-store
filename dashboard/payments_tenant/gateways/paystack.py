"""
dashboard/payments_tenant/gateways/paystack.py
==============================================
Paystack concrete gateway implementation.

Delegates all HTTP work to the existing battle-tested functions in
``provider_checkout.py`` so we don't duplicate any gateway logic.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from .base import BaseGateway, GatewayInitResult, GatewayVerifyResult

logger = logging.getLogger("payments.gateway.paystack")


class PaystackGateway(BaseGateway):
    """Paystack-specific gateway adapter."""

    provider = "paystack"

    # ── initialize ──────────────────────────────────────────────────────────

    def initialize_payment(self, *, intent, gateway_mode, split_params: dict) -> GatewayInitResult:
        from dashboard.payments_tenant.services.provider_checkout import (
            _initialize_paystack,
            HostedCheckoutInitResult,
        )

        result: HostedCheckoutInitResult = _initialize_paystack(intent, gateway_mode, split_params)
        return GatewayInitResult(
            success=result.success,
            provider=self.provider,
            reference=result.reference,
            authorization_url=result.authorization_url,
            access_code=result.access_code,
            gateway_intent_id=result.gateway_intent_id,
            public_key=result.public_key,
            is_redirect=result.is_redirect,
            raw_response=result.raw_response,
            error=result.error,
        )

    # ── verify ───────────────────────────────────────────────────────────────

    def verify_payment(self, *, intent, payload: dict, headers: dict | None = None) -> GatewayVerifyResult:
        from dashboard.payments_tenant.services.provider_checkout import _verify_paystack

        result = _verify_paystack(intent, payload)
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
        Paystack signs webhooks with HMAC-SHA512 of the raw request body, using
        the Paystack secret key as the HMAC key.  The resulting hex digest is
        placed in the ``X-Paystack-Signature`` header.
        """
        if not secret or not signature:
            logger.warning("Paystack webhook: missing secret or signature header.")
            return False
        try:
            expected = hmac.new(
                secret.encode("utf-8"), payload_bytes, hashlib.sha512
            ).hexdigest()
            return hmac.compare_digest(expected, signature.lower())
        except Exception:
            logger.exception("Paystack webhook signature validation error.")
            return False
