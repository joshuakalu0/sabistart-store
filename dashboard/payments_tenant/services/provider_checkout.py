from __future__ import annotations

import json
import logging
import ipaddress
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from dashboard.payments_tenant.services.gateway import get_effective_credentials

logger = logging.getLogger("payments.gateway_checkout")

ZERO_DECIMAL_CURRENCIES = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "JPY",
    "KMF",
    "KRW",
    "MGA",
    "PYG",
    "RWF",
    "UGX",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}


@dataclass
class HostedCheckoutInitResult:
    success: bool
    provider: str = ""
    reference: str = ""
    authorization_url: str = ""
    access_code: str = ""
    client_secret: str = ""
    gateway_intent_id: str = ""
    public_key: str = ""
    is_redirect: bool = True
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class HostedCheckoutVerificationResult:
    success: bool
    provider: str = ""
    payment_status: str = ""
    gateway_reference: str = ""
    gateway_transaction_id: str = ""
    amount: Decimal = Decimal("0.00")
    currency: str = ""
    payment_channel: str = ""
    gateway_message: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def initialize_gateway_checkout(intent, gateway_mode, split_params: dict) -> dict:
    provider = gateway_mode.gateway.provider
    if provider == "paystack":
        result = _initialize_paystack(intent, gateway_mode, split_params)
    elif provider == "flutterwave":
        result = _initialize_flutterwave(intent, gateway_mode, split_params)
    elif provider == "stripe":
        result = _initialize_stripe(intent, gateway_mode, split_params)
    elif provider in {"manual", "cod"}:
        result = HostedCheckoutInitResult(
            success=True,
            provider=provider,
            reference=intent.gateway_intent_id,
            gateway_intent_id=intent.gateway_intent_id,
            authorization_url="",
            is_redirect=False,
            raw_response={"provider": provider, "flow": "internal"},
        )
    else:
        raise ValueError(
            f"Hosted checkout is not implemented yet for gateway provider '{provider}'."
        )

    if not result.success:
        raise ValueError(result.error or f"Unable to initialize {provider} checkout.")

    return {
        "reference": result.reference or result.gateway_intent_id or intent.gateway_intent_id,
        "authorization_url": result.authorization_url,
        "access_code": result.access_code,
        "client_secret": result.client_secret,
        "public_key": result.public_key,
        "gateway_intent_id": result.gateway_intent_id or result.reference or intent.gateway_intent_id,
        "raw_response": result.raw_response,
    }


def verify_gateway_checkout(intent, payload: dict | None = None, headers: dict | None = None) -> HostedCheckoutVerificationResult:
    payload = payload or {}
    provider = intent.gateway_mode.gateway.provider

    if provider == "paystack":
        return _verify_paystack(intent, payload)
    if provider == "flutterwave":
        return _verify_flutterwave(intent, payload)
    if provider == "stripe":
        return _verify_stripe(intent, payload)
    if provider in {"manual", "cod"}:
        return HostedCheckoutVerificationResult(
            success=True,
            provider=provider,
            payment_status=(payload.get("status") or "pending").lower(),
            gateway_reference=intent.gateway_intent_id,
            gateway_transaction_id=intent.gateway_intent_id,
            amount=intent.amount,
            currency=intent.currency,
            raw_response=payload,
        )
    return HostedCheckoutVerificationResult(
        success=False,
        provider=provider,
        error=f"Verification is not implemented yet for gateway provider '{provider}'.",
    )


def _initialize_paystack(intent, gateway_mode, split_params: dict) -> HostedCheckoutInitResult:
    credentials = get_effective_credentials(gateway_mode)
    if not credentials.get("secret_key"):
        return HostedCheckoutInitResult(
            success=False,
            provider="paystack",
            error="Paystack secret key is missing from the active gateway credential.",
        )
    if not intent.customer_email:
        return HostedCheckoutInitResult(
            success=False,
            provider="paystack",
            error="Paystack checkout requires a customer email address.",
        )
    payload = {
        "amount": _to_minor_units(intent.amount, intent.currency),
        "email": intent.customer_email,
        "reference": intent.gateway_intent_id,
        "currency": intent.currency,
        "metadata": {
            **(intent.metadata or {}),
            "payment_intent_id": str(intent.id),
            "cancel_url": intent.cancel_url,
        },
    }
    callback_url = intent.callback_url or intent.success_url
    if callback_url:
        payload["callback_url"] = callback_url
    if split_params.get("subaccount"):
        payload["subaccount"] = split_params["subaccount"]
    transaction_charge_minor = split_params.get("transaction_charge_minor")
    if transaction_charge_minor is None and split_params.get("transaction_charge") is not None:
        transaction_charge_minor = _to_minor_units(
            Decimal(str(split_params["transaction_charge"])),
            intent.currency,
        )
    if transaction_charge_minor is not None:
        transaction_charge_minor = int(transaction_charge_minor)
        if transaction_charge_minor < 0:
            return HostedCheckoutInitResult(
                success=False,
                provider="paystack",
                error="The configured Paystack platform commission cannot be negative.",
                raw_response={"split_params": split_params},
            )
        if transaction_charge_minor > payload["amount"]:
            return HostedCheckoutInitResult(
                success=False,
                provider="paystack",
                error=(
                    "The configured Paystack platform commission is larger than the purchase amount. "
                    "Reduce the split percentage or commission rule for this gateway."
                ),
                raw_response={"split_params": split_params, "amount_minor": payload["amount"]},
            )
        payload["transaction_charge"] = transaction_charge_minor
    if split_params.get("bearer"):
        payload["bearer"] = split_params["bearer"]

    response = _json_request(
        "POST",
        "https://api.paystack.co/transaction/initialize",
        headers={
            "Authorization": f"Bearer {credentials['secret_key']}",
            "Content-Type": "application/json",
        },
        json_body=payload,
    )
    if not response.get("status"):
        return HostedCheckoutInitResult(
            success=False,
            provider="paystack",
            error=_format_provider_error(
                "paystack",
                response,
                "Paystack initialization failed.",
                callback_url=callback_url,
            ),
            raw_response=response,
        )
    data = response.get("data", {})
    return HostedCheckoutInitResult(
        success=True,
        provider="paystack",
        reference=data.get("reference", intent.gateway_intent_id),
        authorization_url=data.get("authorization_url", ""),
        access_code=data.get("access_code", ""),
        gateway_intent_id=data.get("reference", intent.gateway_intent_id),
        public_key=credentials.get("public_key", ""),
        raw_response=response,
    )


def _verify_paystack(intent, payload: dict) -> HostedCheckoutVerificationResult:
    credentials = get_effective_credentials(intent.gateway_mode)
    reference = (
        payload.get("reference")
        or payload.get("trxref")
        or payload.get("gateway_reference")
        or intent.gateway_intent_id
    )
    response = _json_request(
        "GET",
        f"https://api.paystack.co/transaction/verify/{urllib.parse.quote(str(reference))}",
        headers={"Authorization": f"Bearer {credentials['secret_key']}"},
    )
    if not response.get("status"):
        return HostedCheckoutVerificationResult(
            success=False,
            provider="paystack",
            error=response.get("message", "Paystack verification failed."),
            raw_response=response,
        )
    data = response.get("data", {})
    paid = data.get("status") == "success"
    return HostedCheckoutVerificationResult(
        success=True,
        provider="paystack",
        payment_status="success" if paid else "failed",
        gateway_reference=data.get("reference", str(reference)),
        gateway_transaction_id=str(data.get("id", "")),
        amount=_from_minor_units(data.get("amount", 0), data.get("currency") or intent.currency),
        currency=data.get("currency") or intent.currency,
        payment_channel=data.get("channel", ""),
        gateway_message=data.get("gateway_response", ""),
        raw_response=response,
    )


def _initialize_flutterwave(intent, gateway_mode, split_params: dict) -> HostedCheckoutInitResult:
    credentials = get_effective_credentials(gateway_mode)
    if not credentials.get("secret_key"):
        return HostedCheckoutInitResult(
            success=False,
            provider="flutterwave",
            error="Flutterwave secret key is missing from the active gateway credential.",
        )
    if not intent.customer_email:
        return HostedCheckoutInitResult(
            success=False,
            provider="flutterwave",
            error="Flutterwave checkout requires a customer email address.",
        )
    meta = {
        **(intent.metadata or {}),
        "payment_intent_id": str(intent.id),
        "reference": intent.gateway_intent_id,
    }
    if split_params:
        meta["split_params"] = split_params
    payload = {
        "tx_ref": intent.gateway_intent_id,
        "amount": str(intent.amount),
        "currency": intent.currency,
        "redirect_url": intent.callback_url or intent.success_url,
        "payment_options": "card,banktransfer,ussd",
        "customer": {
            "email": intent.customer_email,
            "name": intent.customer_name or intent.customer_email or "Marketplace customer",
            "phonenumber": intent.customer_phone,
        },
        "customizations": {
            "title": intent.order_number or "Marketplace purchase",
            "description": f"Marketplace checkout for {intent.order_number or intent.gateway_intent_id}",
        },
        "meta": meta,
    }

    response = _json_request(
        "POST",
        "https://api.flutterwave.com/v3/payments",
        headers={
            "Authorization": f"Bearer {credentials['secret_key']}",
            "Content-Type": "application/json",
        },
        json_body=payload,
    )
    if response.get("status") != "success":
        return HostedCheckoutInitResult(
            success=False,
            provider="flutterwave",
            error=_format_provider_error(
                "flutterwave",
                response,
                "Flutterwave initialization failed.",
                callback_url=intent.callback_url or intent.success_url,
            ),
            raw_response=response,
        )
    data = response.get("data", {})
    return HostedCheckoutInitResult(
        success=True,
        provider="flutterwave",
        reference=intent.gateway_intent_id,
        authorization_url=data.get("link", ""),
        gateway_intent_id=intent.gateway_intent_id,
        public_key=credentials.get("public_key", ""),
        raw_response=response,
    )


def _verify_flutterwave(intent, payload: dict) -> HostedCheckoutVerificationResult:
    credentials = get_effective_credentials(intent.gateway_mode)
    transaction_id = (
        payload.get("transaction_id")
        or payload.get("id")
        or (payload.get("data") or {}).get("id")
    )
    if not transaction_id:
        return HostedCheckoutVerificationResult(
            success=False,
            provider="flutterwave",
            error="Flutterwave callback did not include a transaction id.",
            raw_response=payload,
        )

    response = _json_request(
        "GET",
        f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify",
        headers={"Authorization": f"Bearer {credentials['secret_key']}"},
    )
    if response.get("status") != "success":
        return HostedCheckoutVerificationResult(
            success=False,
            provider="flutterwave",
            error=response.get("message", "Flutterwave verification failed."),
            raw_response=response,
        )
    data = response.get("data", {})
    paid = data.get("status") == "successful"
    return HostedCheckoutVerificationResult(
        success=True,
        provider="flutterwave",
        payment_status="success" if paid else "failed",
        gateway_reference=data.get("tx_ref", intent.gateway_intent_id),
        gateway_transaction_id=str(data.get("id", transaction_id)),
        amount=Decimal(str(data.get("amount", intent.amount))),
        currency=data.get("currency") or intent.currency,
        payment_channel=data.get("payment_type", ""),
        gateway_message=data.get("processor_response", ""),
        raw_response=response,
    )


def _initialize_stripe(intent, gateway_mode, split_params: dict) -> HostedCheckoutInitResult:
    credentials = get_effective_credentials(gateway_mode)
    if not credentials.get("secret_key"):
        return HostedCheckoutInitResult(
            success=False,
            provider="stripe",
            error="Stripe secret key is missing from the active gateway credential.",
        )
    if not intent.customer_email:
        return HostedCheckoutInitResult(
            success=False,
            provider="stripe",
            error="Stripe checkout requires a customer email address.",
        )
    success_url = _append_query_params(
        intent.callback_url or intent.success_url,
        {"provider": "stripe", "session_id": "{CHECKOUT_SESSION_ID}"},
    )
    cancel_target = intent.cancel_url or _append_query_params(
        intent.callback_url or intent.failure_url or intent.success_url,
        {"provider": "stripe", "status": "cancelled"},
    )
    payload = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_target,
        "client_reference_id": intent.gateway_intent_id,
        "customer_email": intent.customer_email,
        "metadata[reference]": intent.gateway_intent_id,
        "metadata[payment_intent_id]": str(intent.id),
        "metadata[order_number]": intent.order_number or "",
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": intent.currency.lower(),
        "line_items[0][price_data][unit_amount]": str(_to_minor_units(intent.amount, intent.currency)),
        "line_items[0][price_data][product_data][name]": intent.order_number or "Marketplace purchase",
    }
    response = _form_request(
        "POST",
        "https://api.stripe.com/v1/checkout/sessions",
        headers={"Authorization": f"Bearer {credentials['secret_key']}"},
        form_body=payload,
    )
    if response.get("error"):
        error = response["error"]
        return HostedCheckoutInitResult(
            success=False,
            provider="stripe",
            error=_format_provider_error(
                "stripe",
                response,
                "Stripe checkout initialization failed.",
                callback_url=intent.callback_url or intent.success_url,
            ),
            raw_response=response,
        )
    return HostedCheckoutInitResult(
        success=True,
        provider="stripe",
        reference=intent.gateway_intent_id,
        authorization_url=response.get("url", ""),
        access_code=response.get("id", ""),
        gateway_intent_id=intent.gateway_intent_id,
        public_key=credentials.get("public_key", ""),
        raw_response=response,
    )


def _verify_stripe(intent, payload: dict) -> HostedCheckoutVerificationResult:
    credentials = get_effective_credentials(intent.gateway_mode)
    session_id = payload.get("session_id") or payload.get("id")
    if not session_id:
        data = payload.get("data") or {}
        if isinstance(data, dict):
            session_id = (data.get("object") or {}).get("id")
    if not session_id:
        return HostedCheckoutVerificationResult(
            success=False,
            provider="stripe",
            error="Stripe callback did not include a checkout session id.",
            raw_response=payload,
        )

    response = _form_request(
        "GET",
        f"https://api.stripe.com/v1/checkout/sessions/{urllib.parse.quote(str(session_id))}",
        headers={"Authorization": f"Bearer {credentials['secret_key']}"},
        form_body={"expand[]": ["payment_intent"]},
    )
    if response.get("error"):
        error = response["error"]
        return HostedCheckoutVerificationResult(
            success=False,
            provider="stripe",
            error=error.get("message", "Stripe verification failed."),
            raw_response=response,
        )

    payment_status = response.get("payment_status", "")
    paid = payment_status == "paid"
    payment_intent = response.get("payment_intent")
    if isinstance(payment_intent, dict):
        gateway_transaction_id = payment_intent.get("id", "")
    else:
        gateway_transaction_id = payment_intent or ""
    amount_total = response.get("amount_total", 0)
    currency = (response.get("currency") or intent.currency).upper()
    return HostedCheckoutVerificationResult(
        success=True,
        provider="stripe",
        payment_status="success" if paid else "failed",
        gateway_reference=response.get("client_reference_id") or intent.gateway_intent_id,
        gateway_transaction_id=gateway_transaction_id,
        amount=_from_minor_units(amount_total, currency),
        currency=currency,
        payment_channel="card",
        gateway_message=response.get("status", ""),
        raw_response=response,
    )


def _json_request(method: str, url: str, *, headers: dict[str, str] | None = None, json_body: dict | None = None) -> dict:
    data = None
    request_headers = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return _decode_error_body(body, default_message=str(exc))
    except urllib.error.URLError as exc:
        return {"status": False, "message": str(exc)}


def _form_request(method: str, url: str, *, headers: dict[str, str] | None = None, form_body: dict[str, Any] | None = None) -> dict:
    data = None
    request_headers = dict(headers or {})
    if form_body:
        encoded = urllib.parse.urlencode(form_body, doseq=True)
        data = encoded.encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return _decode_error_body(body, default_message=str(exc))
    except urllib.error.URLError as exc:
        return {"error": {"message": str(exc)}}


def _decode_error_body(body: str, *, default_message: str) -> dict:
    if not body:
        return {"status": False, "message": default_message}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"status": False, "message": body or default_message}


def _format_provider_error(provider: str, response: dict[str, Any], fallback: str, *, callback_url: str = "") -> str:
    message = (
        response.get("message")
        or (response.get("error") or {}).get("message")
        or (response.get("data") or {}).get("message")
        or fallback
    )
    code = response.get("code") or (response.get("error") or {}).get("code")
    if code:
        message = f"{message} (code: {code})"
    if callback_url and _looks_like_local_callback(callback_url):
        message += (
            " The callback URL currently points to a local development host. "
            "Some hosted gateways reject localhost or private-network callback URLs. "
            "Use a public tunnel or production domain for gateway redirects."
        )
    return message


def _looks_like_local_callback(url: str) -> bool:
    hostname = urllib.parse.urlsplit(url).hostname or ""
    if not hostname:
        return False
    lowered = hostname.lower()
    if lowered in {"localhost", "127.0.0.1", "::1"} or lowered.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(lowered).is_private or ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def _to_minor_units(amount: Decimal, currency: str) -> int:
    currency = (currency or "").upper()
    if currency in ZERO_DECIMAL_CURRENCIES:
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _from_minor_units(amount: int | str | Decimal, currency: str) -> Decimal:
    currency = (currency or "").upper()
    value = Decimal(str(amount or 0))
    if currency in ZERO_DECIMAL_CURRENCIES:
        return value.quantize(Decimal("0.01"))
    return (value / Decimal("100")).quantize(Decimal("0.01"))


def _append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.update({k: v for k, v in params.items() if v != ""})
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query),
            parsed.fragment,
        )
    )


# ─────────────────────────────────────────────────────────────
# GATEWAY REGISTRY FAÇADE
# ─────────────────────────────────────────────────────────────

def validate_webhook_signature_for_provider(
    *,
    provider: str,
    payload_bytes: bytes,
    signature: str,
    secret: str,
) -> bool:
    """
    Validate the HMAC/shared-secret signature on an incoming webhook using
    the correct algorithm for *provider*.

    This is the single public entry point for webhook signature validation.
    It delegates to the appropriate concrete gateway class via the registry,
    so callers never need to implement provider-specific HMAC logic themselves.

    Parameters
    ----------
    provider      : Gateway slug, e.g. "paystack" | "flutterwave" | "stripe"
    payload_bytes : Raw HTTP request body (bytes)
    signature     : The signature value from the gateway's header
    secret        : Webhook signing secret (NEVER log this)

    Returns True only when the signature is cryptographically valid.
    Returns False (does not raise) when:
      - The provider is not registered in the gateway registry.
      - Any error occurs during HMAC computation.
    """
    try:
        from dashboard.payments_tenant.gateways import gateway_registry
        gw = gateway_registry.get(provider)
        return gw.validate_webhook_signature(
            payload_bytes=payload_bytes,
            signature=signature,
            secret=secret,
        )
    except ValueError:
        logger.warning(
            "validate_webhook_signature_for_provider: unknown provider '%s'.", provider
        )
        return False
    except Exception:
        logger.exception(
            "validate_webhook_signature_for_provider: unexpected error for provider '%s'.", provider
        )
        return False
