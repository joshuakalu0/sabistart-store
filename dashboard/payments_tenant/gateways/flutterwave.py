"""
dashboard/payments_tenant/gateways/flutterwave.py
=================================================
Flutterwave concrete gateway implementation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from .base import BaseGateway, GatewayInitResult, GatewayVerifyResult

logger = logging.getLogger("payments.gateway.flutterwave")


class FlutterwaveGateway(BaseGateway):
    """Flutterwave-specific gateway adapter."""

    provider = "flutterwave"

    # ── initialize ──────────────────────────────────────────────────────────

    def initialize_payment(self, *, intent, gateway_mode, split_params: dict) -> GatewayInitResult:
        from dashboard.payments_tenant.services.provider_checkout import (
            _initialize_flutterwave,
        )

        result = _initialize_flutterwave(intent, gateway_mode, split_params)
        return GatewayInitResult(
            success=result.success,
            provider=self.provider,
            reference=result.reference,
            authorization_url=result.authorization_url,
            gateway_intent_id=result.gateway_intent_id,
            public_key=result.public_key,
            is_redirect=result.is_redirect,
            raw_response=result.raw_response,
            error=result.error,
        )

    # ── verify ───────────────────────────────────────────────────────────────

    def verify_payment(self, *, intent, payload: dict, headers: dict | None = None) -> GatewayVerifyResult:
        from dashboard.payments_tenant.services.provider_checkout import _verify_flutterwave

        result = _verify_flutterwave(intent, payload)
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
        Flutterwave sends the verif-hash (set when creating the webhook in the
        dashboard) in the ``verif-hash`` header.  Simple equality check —
        Flutterwave does NOT use HMAC for webhook verification; they use a
        static shared secret.
        """
        if not secret or not signature:
            logger.warning("Flutterwave webhook: missing secret or verif-hash header.")
            return False
        return hmac.compare_digest(secret.strip(), signature.strip())
