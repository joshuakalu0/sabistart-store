"""
payments/utils/gateway.py
===========================
Gateway mode resolution, credential routing, and PLATFORM/DIRECT switching.

This module is the entry point for all payment processing decisions:
  - Which gateway to use for a checkout
  - Which API keys to use (platform's or tenant's own)
  - How to build split-payment parameters for Paystack/Flutterwave
  - How to switch a tenant between PLATFORM and DIRECT modes

The dual-mode design means every function here considers mode first:
  PLATFORM MODE → use PlatformGatewayCredential
  DIRECT MODE   → use TenantGatewayCredential
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("payments.gateway")


@dataclass
class GatewayResolutionResult:
    success: bool = False
    gateway_mode_id: Optional[str] = None
    gateway_provider: str = ""
    mode: str = ""
    public_key: str = ""
    is_test: bool = False
    subaccount_code: str = ""
    split_percentage: Optional[Decimal] = None
    message: str = ""
    errors: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — GATEWAY RESOLUTION
# ─────────────────────────────────────────────────────────────

def get_default_gateway(payment_profile):
    """Return the default active TenantGatewayMode for a payment profile."""
    from dashboard.payments_tenant.models import TenantGatewayMode

    return TenantGatewayMode.objects.filter(
        payment_profile=payment_profile,
        is_default=True,
        status=TenantGatewayMode.ActivationStatus.ACTIVE,
    ).select_related("gateway", "platform_credential", "direct_credential").first()


def get_active_gateway_mode(payment_profile, gateway_provider: str = None):
    """
    Resolve the active TenantGatewayMode for a tenant.

    If gateway_provider is given, returns that specific gateway's mode.
    Otherwise returns the default active gateway.
    """
    from dashboard.payments_tenant.models import TenantGatewayMode

    qs = TenantGatewayMode.objects.filter(
        payment_profile=payment_profile,
        status=TenantGatewayMode.ActivationStatus.ACTIVE,
    ).select_related("gateway", "platform_credential", "direct_credential")

    if gateway_provider:
        return qs.filter(gateway__provider=gateway_provider).first()
    return qs.filter(is_default=True).first() or qs.first()


def list_tenant_gateways(payment_profile, active_only: bool = True) -> list:
    """
    List all configured gateways for a tenant with their mode and status.

    Returns:
        list[dict]: Gateway summaries with mode, status, and capability flags.
    """
    from dashboard.payments_tenant.models import TenantGatewayMode

    qs = TenantGatewayMode.objects.filter(
        payment_profile=payment_profile,
    ).select_related("gateway", "direct_credential")

    if active_only:
        qs = qs.filter(status=TenantGatewayMode.ActivationStatus.ACTIVE)

    return [
        {
            "id": str(gm.id),
            "gateway_provider": gm.gateway.provider,
            "gateway_name": gm.gateway.name,
            "mode": gm.mode,
            "is_platform_mode": gm.is_platform_mode,
            "is_direct_mode": gm.is_direct_mode,
            "status": gm.status,
            "is_default": gm.is_default,
            "has_own_credentials": gm.direct_credential is not None,
            "subaccount_code": gm.platform_subaccount_code,
            "split_percentage": float(gm.split_percentage) if gm.split_percentage else None,
            "accepted_currencies": gm.accepted_currencies,
            "total_transactions": gm.total_transactions,
            "total_volume": float(gm.total_volume),
            "checkout_label": gm.checkout_label or gm.gateway.name,
            "checkout_display_order": gm.checkout_display_order,
            "last_transaction_at": gm.last_transaction_at.isoformat() if gm.last_transaction_at else None,
            "supports_3ds": gm.gateway.supports_3ds,
            "supports_recurring": gm.gateway.supports_recurring,
            "supports_split_payment": gm.gateway.supports_split_payment,
        }
        for gm in qs.order_by("-is_default", "gateway__display_order")
    ]


def resolve_gateway_for_checkout(
    payment_profile,
    currency: str = None,
    payment_method: str = None,
    gateway_provider: str = None,
    amount: Decimal = None,
) -> GatewayResolutionResult:
    """
    Determine the best gateway for a checkout given the constraints.

    Resolution priority:
      1. Explicit gateway_provider if given
      2. Currency-preferred gateway (SupportedCurrency.preferred_gateway)
      3. Default gateway (TenantGatewayMode.is_default=True)
      4. Any active gateway

    Returns a GatewayResolutionResult with all the data needed to
    initialize a payment widget on the frontend.
    """
    from dashboard.payments_tenant.models import TenantGatewayMode, SupportedCurrency, PaymentMode

    gateway_mode = None

    # Try explicit provider first
    if gateway_provider:
        gateway_mode = TenantGatewayMode.objects.filter(
            payment_profile=payment_profile,
            gateway__provider=gateway_provider,
            status=TenantGatewayMode.ActivationStatus.ACTIVE,
        ).select_related("gateway", "platform_credential", "direct_credential").first()

    # Try currency-preferred gateway
    if not gateway_mode and currency:
        try:
            sc = SupportedCurrency.objects.select_related(
                "preferred_gateway__gateway",
                "preferred_gateway__platform_credential",
                "preferred_gateway__direct_credential",
            ).get(
                payment_profile=payment_profile,
                currency_code=currency,
                is_enabled=True,
            )
            if sc.preferred_gateway and sc.preferred_gateway.is_active:
                gateway_mode = sc.preferred_gateway
        except SupportedCurrency.DoesNotExist:
            pass

    # Fall back to default / any active
    if not gateway_mode:
        gateway_mode = get_active_gateway_mode(payment_profile)

    if not gateway_mode:
        return GatewayResolutionResult(
            success=False,
            errors=["No active payment gateway configured for this store."],
        )

    # Validate amount limits
    if amount is not None:
        gw = gateway_mode.gateway
        if gw.min_transaction_amount and amount < gw.min_transaction_amount:
            return GatewayResolutionResult(
                success=False,
                errors=[f"Amount {amount} is below minimum {gw.min_transaction_amount} for {gw.name}."],
            )
        if gw.max_transaction_amount and amount > gw.max_transaction_amount:
            return GatewayResolutionResult(
                success=False,
                errors=[f"Amount {amount} exceeds maximum {gw.max_transaction_amount} for {gw.name}."],
            )

    # Get the public key for frontend initialization
    public_key = gateway_mode.get_effective_public_key()

    # Determine test mode
    is_test = False
    if gateway_mode.is_direct_mode and gateway_mode.direct_credential:
        is_test = gateway_mode.direct_credential.environment == "test"
    elif gateway_mode.platform_credential:
        is_test = gateway_mode.platform_credential.environment == "test"

    return GatewayResolutionResult(
        success=True,
        gateway_mode_id=str(gateway_mode.id),
        gateway_provider=gateway_mode.gateway.provider,
        mode=gateway_mode.mode,
        public_key=public_key,
        is_test=is_test,
        subaccount_code=gateway_mode.platform_subaccount_code if gateway_mode.is_platform_mode else "",
        split_percentage=gateway_mode.split_percentage,
        message=f"Resolved: {gateway_mode.gateway.name} ({gateway_mode.mode} mode)",
    )


def get_effective_credentials(gateway_mode) -> dict:
    """
    Return the decrypted credentials for backend API calls.
    PLATFORM MODE → platform credential keys
    DIRECT MODE   → tenant's own credential keys

    SECURITY: Use only in backend workers/tasks. Never log or expose.

    Returns:
        dict: {secret_key, public_key, webhook_secret, encryption_key, extra}
    """
    secret_key = gateway_mode.get_effective_secret_key()
    public_key = gateway_mode.get_effective_public_key()

    webhook_secret = ""
    encryption_key = ""
    extra = {}

    if gateway_mode.is_direct_mode and gateway_mode.direct_credential:
        cred = gateway_mode.direct_credential
        webhook_secret = cred.webhook_secret
        encryption_key = cred.encryption_key
        extra = cred.extra_credentials or {}
    elif gateway_mode.platform_credential:
        cred = gateway_mode.platform_credential
        webhook_secret = cred.webhook_secret
        encryption_key = cred.encryption_key
        extra = cred.extra_credentials or {}

    return {
        "secret_key": secret_key,
        "public_key": public_key,
        "webhook_secret": webhook_secret,
        "encryption_key": encryption_key,
        "extra": extra,
        "mode": gateway_mode.mode,
        "provider": gateway_mode.gateway.provider,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — SPLIT PAYMENT PARAMS
# ─────────────────────────────────────────────────────────────

def build_split_payment_params(
    gateway_mode,
    amount: Decimal,
    currency: str,
) -> dict:
    """
    Build gateway-specific split payment parameters for PLATFORM MODE.

    For gateways with native split (Paystack, Flutterwave), the gateway
    automatically routes the commission to the platform and the rest to
    the tenant's subaccount.

    Paystack format:
        subaccount: "ACCT_xxxxx"
        transaction_charge: 2500  (platform's share in kobo/pence)
        bearer: "account"

    Flutterwave format:
        subaccounts: [{"id": "RS_xxxxx", "transaction_charge_type": "flat", "transaction_charge": 250}]

    Returns:
        dict: Gateway-specific split params to include in payment initialization.
    """
    if not gateway_mode.is_platform_mode:
        return {}  # DIRECT MODE: no split needed

    if not gateway_mode.gateway.supports_split_payment:
        return {}  # Gateway doesn't support native split

    if not gateway_mode.platform_subaccount_code:
        logger.warning(
            "Gateway %s supports split but no subaccount_code set for gateway_mode %s",
            gateway_mode.gateway.provider, gateway_mode.id,
        )
        return {}

    provider = gateway_mode.gateway.provider
    split_pct = gateway_mode.split_percentage

    if not split_pct:
        # Fall back to commission-based calculation
        from .commission_balance import resolve_commission_rule
        rule = resolve_commission_rule(gateway_mode.payment_profile, gateway_mode.gateway)
        if rule:
            commission = rule.calculate_commission(amount)
            split_pct = ((amount - commission) / amount * 100).quantize(Decimal("0.0001"))
        else:
            split_pct = Decimal("97.5000")

    platform_share = (amount * (100 - split_pct) / 100).quantize(Decimal("0.01"))

    if provider == "paystack":
        # Paystack expects amount in kobo (smallest currency unit)
        multiplier = Decimal("100") if currency in ("NGN", "GHS", "KES", "ZAR") else Decimal("1")
        platform_charge_minor = int(platform_share * multiplier)
        return {
            "subaccount": gateway_mode.platform_subaccount_code,
            "transaction_charge": platform_share,
            "transaction_charge_minor": platform_charge_minor,
            "bearer": "account",
        }

    elif provider == "flutterwave":
        return {
            "subaccounts": [
                {
                    "id": gateway_mode.platform_subaccount_code,
                    "transaction_charge_type": "flat",
                    "transaction_charge": float(platform_share),
                }
            ]
        }

    return {}


# ─────────────────────────────────────────────────────────────
# SECTION 3 — MODE SWITCHING
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def switch_tenant_to_direct_mode(
    payment_profile,
    gateway_provider: str,
    credential_id: str,
    actor=None,
    reason: str = "Tenant added own gateway credentials",
) -> dict:
    """
    Switch a tenant's gateway from PLATFORM to DIRECT mode.

    Prerequisites:
      - TenantGatewayCredential with credential_id must be ACTIVE
      - Gateway must support direct mode
      - TenantGatewayMode for this gateway must exist

    The switch is atomic — if anything fails, the mode stays unchanged.

    Returns:
        dict: {success, message, previous_mode, new_mode}
    """
    from dashboard.payments_tenant.models import TenantGatewayMode, TenantGatewayCredential, PaymentMode

    try:
        gateway_mode = TenantGatewayMode.objects.select_for_update().select_related(
            "gateway"
        ).get(
            payment_profile=payment_profile,
            gateway__provider=gateway_provider,
        )
    except TenantGatewayMode.DoesNotExist:
        return {"success": False, "message": f"Gateway '{gateway_provider}' not configured."}

    if not gateway_mode.gateway.is_available_for_direct_mode:
        return {
            "success": False,
            "message": f"{gateway_mode.gateway.name} does not support Direct Mode.",
        }

    try:
        credential = TenantGatewayCredential.objects.get(
            id=credential_id,
            payment_profile=payment_profile,
            gateway=gateway_mode.gateway,
            status=TenantGatewayCredential.CredentialStatus.ACTIVE,
        )
    except TenantGatewayCredential.DoesNotExist:
        return {"success": False, "message": "Credential not found or not validated yet."}

    previous_mode = gateway_mode.mode
    gateway_mode.switch_to_direct(credential=credential, actor=actor, reason=reason)

    logger.info(
        "Tenant gateway mode switched: %s → DIRECT for %s (by %s)",
        previous_mode, gateway_provider, actor,
    )

    return {
        "success": True,
        "previous_mode": previous_mode,
        "new_mode": PaymentMode.DIRECT,
        "message": (
            f"{gateway_mode.gateway.name} now uses your own credentials. "
            "Payments will go directly to your account."
        ),
    }


@transaction.atomic
def switch_tenant_to_platform_mode(
    payment_profile,
    gateway_provider: str,
    actor=None,
    reason: str = "Tenant reverted to platform mode",
) -> dict:
    """Switch a tenant's gateway back to PLATFORM mode."""
    from dashboard.payments_tenant.models import TenantGatewayMode, PaymentMode

    try:
        gateway_mode = TenantGatewayMode.objects.select_for_update().select_related(
            "gateway"
        ).get(
            payment_profile=payment_profile,
            gateway__provider=gateway_provider,
        )
    except TenantGatewayMode.DoesNotExist:
        return {"success": False, "message": f"Gateway '{gateway_provider}' not configured."}

    if gateway_mode.is_platform_mode:
        return {"success": True, "message": "Already in platform mode.", "new_mode": PaymentMode.PLATFORM}

    previous_mode = gateway_mode.mode
    gateway_mode.switch_to_platform(actor=actor, reason=reason)

    logger.info(
        "Tenant gateway mode reverted to PLATFORM: %s for %s",
        gateway_provider, actor
    )

    return {
        "success": True,
        "previous_mode": previous_mode,
        "new_mode": PaymentMode.PLATFORM,
        "message": (
            f"{gateway_mode.gateway.name} is back on platform mode. "
            "Your earnings will be credited to your balance and available for payout."
        ),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 4 — CREDENTIAL MANAGEMENT
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def submit_direct_credentials(
    payment_profile,
    gateway_provider: str,
    public_key: str,
    secret_key: str,
    environment: str = "live",
    encryption_key: str = "",
    webhook_secret: str = "",
    extra_credentials: dict = None,
    label: str = "",
    actor=None,
) -> dict:
    """
    Tenant submits their own gateway credentials for DIRECT MODE.

    Creates a TenantGatewayCredential in PENDING status.
    Triggers async validation task.

    Returns:
        dict: {success, credential_id, message}
    """
    from dashboard.payments_tenant.models import TenantGatewayCredential, PaymentGatewayDefinition

    try:
        gateway = PaymentGatewayDefinition.objects.get(
            provider=gateway_provider, is_enabled=True,
        )
    except PaymentGatewayDefinition.DoesNotExist:
        return {"success": False, "message": f"Gateway '{gateway_provider}' is not supported."}

    if not gateway.is_available_for_direct_mode:
        return {
            "success": False,
            "message": f"{gateway.name} is not available for Direct Mode on this platform.",
        }

    # Mark any existing PENDING/TESTING credentials as superseded
    TenantGatewayCredential.objects.filter(
        payment_profile=payment_profile,
        gateway=gateway,
        status__in=[
            TenantGatewayCredential.CredentialStatus.PENDING,
            TenantGatewayCredential.CredentialStatus.TESTING,
        ],
    ).update(
        status=TenantGatewayCredential.CredentialStatus.REVOKED,
        revoke_reason="Superseded by new credential submission.",
        revoked_at=timezone.now(),
    )

    credential = TenantGatewayCredential.objects.create(
        payment_profile=payment_profile,
        gateway=gateway,
        label=label or f"{gateway.name} {environment.title()} Keys",
        status=TenantGatewayCredential.CredentialStatus.PENDING,
        environment=environment,
        public_key=public_key,  # Encrypt in production
        secret_key=secret_key,  # Encrypt in production
        encryption_key=encryption_key,
        webhook_secret=webhook_secret,
        extra_credentials=extra_credentials or {},
        submitted_by=actor,
    )

    # Trigger async validation (stub)
    _schedule_credential_validation(credential)

    return {
        "success": True,
        "credential_id": str(credential.id),
        "message": (
            "Credentials submitted. We'll validate them in the background and notify you. "
            "Once validated, you can activate Direct Mode for this gateway."
        ),
        "status": TenantGatewayCredential.CredentialStatus.PENDING,
    }


def validate_tenant_credentials(credential_id: str) -> dict:
    """
    Validate a TenantGatewayCredential against the gateway's API.
    Called by an async task after submission.

    Returns:
        dict: {success, credential_id, message, account_details}
    """
    from dashboard.payments_tenant.models import TenantGatewayCredential

    try:
        credential = TenantGatewayCredential.objects.select_related("gateway").get(
            id=credential_id
        )
    except TenantGatewayCredential.DoesNotExist:
        return {"success": False, "message": "Credential not found."}

    credential.status = TenantGatewayCredential.CredentialStatus.TESTING
    credential.save(update_fields=["status", "updated_at"])

    try:
        # Stub validation — replace with real gateway API calls in production
        account_details = _call_gateway_validation_api(credential)

        credential.status = TenantGatewayCredential.CredentialStatus.ACTIVE
        credential.validated_at = timezone.now()
        credential.gateway_account_id = account_details.get("account_id", "")
        credential.gateway_business_name = account_details.get("business_name", "")
        credential.gateway_email = account_details.get("email", "")
        credential.validation_note = "Credentials validated successfully."
        credential.save(update_fields=[
            "status", "validated_at", "gateway_account_id",
            "gateway_business_name", "gateway_email", "validation_note", "updated_at",
        ])

        return {
            "success": True,
            "credential_id": str(credential.id),
            "message": "Credentials validated successfully.",
            "account_details": account_details,
        }

    except Exception as e:
        credential.status = TenantGatewayCredential.CredentialStatus.INVALID
        credential.invalid_reason = str(e)
        credential.save(update_fields=["status", "invalid_reason", "updated_at"])

        return {
            "success": False,
            "credential_id": str(credential.id),
            "message": f"Credential validation failed: {e}",
        }


@transaction.atomic
def activate_gateway_mode(
    payment_profile,
    gateway_provider: str,
    actor=None,
) -> dict:
    """Activate an INACTIVE gateway mode for a tenant."""
    from dashboard.payments_tenant.models import TenantGatewayMode

    try:
        gm = TenantGatewayMode.objects.get(
            payment_profile=payment_profile,
            gateway__provider=gateway_provider,
        )
    except TenantGatewayMode.DoesNotExist:
        return {"success": False, "message": "Gateway mode not found."}

    gm.status = TenantGatewayMode.ActivationStatus.ACTIVE
    gm.save(update_fields=["status", "updated_at"])

    return {
        "success": True,
        "message": f"{gm.gateway.name} gateway activated.",
        "mode": gm.mode,
    }


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _schedule_credential_validation(credential) -> None:
    """Enqueue async credential validation task. Replace with real Celery task."""
    logger.info("Credential validation scheduled for %s", credential.id)
    # In production:
    # from payments.tasks import validate_gateway_credentials
    # validate_gateway_credentials.apply_async(args=[str(credential.id)], countdown=5)


def _call_gateway_validation_api(credential) -> dict:
    """
    Call the gateway's account verification API.
    Stub — replace with real provider API calls.
    """
    provider = credential.gateway.provider
    logger.info("Validating credentials for provider=%s (stub)", provider)
    # Production: call Paystack /integration/fetch, Stripe /v1/account, etc.
    return {
        "account_id": f"stub_account_{provider}",
        "business_name": "Validated Business",
        "email": credential.gateway_email or "stub@example.com",
    }
