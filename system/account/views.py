"""
system/account/views.py
=====================
Views for platform-level authentication.

Handles:
- Platform user registration (with automatic tenant creation)
- Platform user login
- Platform user logout
- Password reset
"""

import secrets
import uuid
import re
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.views import View
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context
from django.urls import reverse

from public.utils import rate_limit
from system.account.forms import (
    OnboardingAccountForm,
    OnboardingCheckoutForm,
    OnboardingPlanForm,
    OnboardingSubdomainForm,
    PlatformRegistrationForm,
    PlatformLoginForm,
    PlatformPasswordResetRequestForm,
)
from system.account.models import OnboardingSession, PlatformUser
from system.account.services import TenantService, TenantCreationError
from system.core.models import Shop, Domain
from dashboard.feature_marketplace.services import grant_manual_entitlement
from system.feature_marketplace.models import FeatureDefinition, FeaturePrice, FeatureType, FeaturePurchaseIndex
from dashboard.feature_marketplace.models import FeaturePurchase, TenantEntitlement
from dashboard.feature_marketplace.services.checkout import create_purchase, initialize_purchase_payment
from system.feature_marketplace.services import (
    get_active_feature_catalog,
    get_marketplace_gateways,
    get_plan_bundle_by_slug,
    get_plan_bundles,
    get_plan_groups,
)


SCHEMA_AWARE_BACKEND = "sabistart.auth_backends.SchemaAwareAuthenticationBackend"
SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
RESERVED_SUBDOMAINS = {
    "www",
    "admin",
    "mail",
    "ftp",
    "localhost",
    "api",
    "blog",
    "shop",
    "store",
    "platform",
    "public",
    "private",
}


def _get_existing_onboarding_session(request) -> OnboardingSession | None:
    token = request.session.get("platform_onboarding_token")
    if token:
        session = (
            OnboardingSession.objects.filter(session_token=token)
            .exclude(status__in=[OnboardingSession.Status.COMPLETED, OnboardingSession.Status.CANCELLED])
            .first()
        )
        if session:
            return session

    if getattr(request.user, "is_authenticated", False) and getattr(request.user, "email", ""):
        session = (
            OnboardingSession.objects.filter(email__iexact=request.user.email)
            .exclude(status__in=[OnboardingSession.Status.COMPLETED, OnboardingSession.Status.CANCELLED])
            .order_by("-updated_at")
            .first()
        )
        if session:
            request.session["platform_onboarding_token"] = session.session_token
            request.session.modified = True
            return session

        user_id = str(getattr(request.user, "id", ""))
        if user_id:
            session = (
                OnboardingSession.objects.filter(metadata__platform_user_id=user_id)
                .exclude(status__in=[OnboardingSession.Status.COMPLETED, OnboardingSession.Status.CANCELLED])
                .order_by("-updated_at")
                .first()
            )
            if session:
                request.session["platform_onboarding_token"] = session.session_token
                request.session.modified = True
                return session
    return None


def _get_or_create_onboarding_session(request) -> OnboardingSession:
    session = _get_existing_onboarding_session(request)
    if session:
        return session
    session = OnboardingSession.objects.create(session_token=secrets.token_urlsafe(24))
    request.session["platform_onboarding_token"] = session.session_token
    request.session.modified = True
    return session


def _validate_subdomain_candidate(raw_value: str) -> str:
    candidate = (raw_value or "").strip().lower()
    if not candidate:
        raise ValidationError("Please enter a subdomain.")
    if len(candidate) < 3 or len(candidate) > 50:
        raise ValidationError("Subdomain must be between 3 and 50 characters long.")
    if candidate in RESERVED_SUBDOMAINS:
        raise ValidationError(f"'{candidate}' is a reserved subdomain.")
    if not SUBDOMAIN_PATTERN.match(candidate):
        raise ValidationError(
            "Subdomain can only contain lowercase letters, numbers, and hyphens, and cannot start or end with a hyphen."
        )
    return candidate


def _formatted_store_domain(request, subdomain: str) -> str:
    suffix = (getattr(settings, "SUBDOMAIN_SUFFIX", "") or "").strip().lstrip(".")
    if not suffix:
        return subdomain
    return f"{subdomain}.{suffix}"


def _platform_domain_suffix(request) -> str:
    suffix = (getattr(settings, "SUBDOMAIN_SUFFIX", "") or "").strip().lstrip(".")
    if suffix:
        return suffix
    host = (request.get_host() or "").split(":")[0].strip(".")
    return host or "localhost"


def _onboarding_context(request, *, session: OnboardingSession, page_title: str, current_step: str, **extra):
    context = {
        "page_title": page_title,
        "progress_steps": _onboarding_progress(current_step),
        "onboarding_session": session,
        "platform_domain_suffix": _platform_domain_suffix(request),
    }
    context.update(extra)
    return context


def _resume_onboarding_url(session: OnboardingSession) -> str:
    metadata = session.metadata or {}
    if not session.email or not session.business_name or not metadata.get("password_hash"):
        return reverse("platform:onboarding_account")
    if not session.selected_bundle_slug:
        return reverse("platform:onboarding_plan")
    if session.payment_status != OnboardingSession.PaymentStatus.PAID:
        return reverse("platform:onboarding_checkout")
    if not session.desired_subdomain or not metadata.get("tenant_schema_name"):
        return reverse("platform:onboarding_subdomain")
    return reverse("platform:onboarding_provisioning")


def _onboarding_progress(current_step: str):
    steps = (
        ("start", "Welcome"),
        ("account", "Account"),
        ("plan", "Plan"),
        ("checkout", "Payment"),
        ("subdomain", "Store Setup"),
    )
    return [
        {
            "key": key,
            "label": label,
            "active": key == current_step,
        }
        for key, label in steps
    ]


def _bundle_choices(currency: str = "NGN"):
    choices = [("", "Choose a plan")]
    for bundle in get_plan_bundles(currency=currency, current_only=True):
        label = f"{bundle.name} ({bundle.currency} {bundle.price}/{bundle.billing_cycle})"
        choices.append((bundle.slug, label))
    return choices


def _addon_choices(currency: str = "NGN"):
    return []


def _estimate_onboarding_total(*, bundle_slug: str = "", addon_codes: list[str] | None = None, currency: str = "NGN") -> Decimal:
    addon_codes = addon_codes or []
    total = Decimal("0.00")
    bundle = get_plan_bundle_by_slug(bundle_slug, currency=currency)
    if bundle:
        total += bundle.price
    return total.quantize(Decimal("0.01"))


def _sorted_marketplace_gateways(currency: str = "NGN") -> list[dict]:
    gateways = list(get_marketplace_gateways(currency=currency))
    return sorted(
        gateways,
        key=lambda gateway: (
            0 if gateway["provider"] == "flutterwave" else (1 if gateway["provider"] == "paystack" else 2),
            gateway.get("display_order", 0),
            gateway["name"],
        ),
    )


def _gateway_choices(currency: str = "NGN"):
    return [
        (gateway["provider"], f'{gateway["name"]} ({gateway["environment"]})')
        for gateway in _sorted_marketplace_gateways(currency=currency)
    ]


def _selected_gateway(currency: str, provider: str):
    for gateway in _sorted_marketplace_gateways(currency=currency):
        if gateway["provider"] == provider:
            return gateway
    return None


def _remember_requested_plan(request, session: OnboardingSession) -> str:
    requested_plan = (request.GET.get("plan") or "").strip()
    if not requested_plan:
        return ""
    if not get_plan_bundle_by_slug(requested_plan, currency=session.currency):
        return ""
    metadata = {**(session.metadata or {}), "requested_plan_slug": requested_plan}
    session.metadata = metadata
    session.save(update_fields=["metadata", "updated_at"])
    return requested_plan


def _ensure_onboarding_payment_reference(session: OnboardingSession) -> str:
    metadata = dict(session.metadata or {})
    payment_reference = metadata.get("payment_reference", "")
    if payment_reference:
        return payment_reference
    payment_reference = f"onb_{session.session_token[:10]}_{secrets.token_hex(4)}"
    metadata["payment_reference"] = payment_reference
    session.metadata = metadata
    session.save(update_fields=["metadata", "updated_at"])
    return payment_reference


def _ensure_onboarding_checkout_reference(session: OnboardingSession) -> str:
    metadata = dict(session.metadata or {})
    checkout_reference = metadata.get("checkout_reference", "")
    if checkout_reference:
        return checkout_reference
    checkout_reference = f"chk_{session.session_token[:10]}_{secrets.token_hex(3)}"
    metadata["checkout_reference"] = checkout_reference
    session.metadata = metadata
    session.save(update_fields=["metadata", "updated_at"])
    return checkout_reference


def _init_pre_tenant_payment(
    *,
    gateway_provider: str,
    bundle,
    session: OnboardingSession,
    callback_url: str,
    cancel_url: str,
) -> dict:
    from system.system_pay.models import PaymentGatewayDefinition
    from dashboard.payments_tenant.services.provider_checkout import (
        _json_request,
        _to_minor_units,
        _format_provider_error,
    )

    gateway_def = PaymentGatewayDefinition.objects.filter(provider=gateway_provider, is_enabled=True).first()
    if not gateway_def:
        return {"success": False, "error": f"Payment gateway '{gateway_provider}' is not enabled on this platform."}

    cred = gateway_def.platform_credentials.filter(is_active=True).order_by("-priority", "-created_at").first()
    if not cred or not cred.secret_key:
        return {"success": False, "error": f"Active platform API keys for '{gateway_provider}' are missing."}

    tx_ref = f"ONB-{uuid.uuid4().hex[:12].upper()}"
    secret_key = cred.secret_key.strip()
    customer_email = session.email
    customer_name = f"{session.first_name} {session.last_name}".strip() or session.business_name or session.email

    if gateway_provider == "flutterwave":
        payload = {
            "tx_ref": tx_ref,
            "amount": str(bundle.price),
            "currency": bundle.currency,
            "redirect_url": callback_url,
            "payment_options": "card,banktransfer,ussd",
            "customer": {
                "email": customer_email,
                "name": customer_name,
            },
            "customizations": {
                "title": f"SabiStart - {bundle.name}",
                "description": f"Subscription plan for {session.business_name or 'store'}",
            },
            "meta": {
                "session_token": session.session_token,
                "bundle_slug": bundle.slug,
                "source": "onboarding_pre_tenant",
            },
        }
        res = _json_request(
            "POST",
            "https://api.flutterwave.com/v3/payments",
            headers={"Authorization": f"Bearer {secret_key}"},
            json_body=payload,
        )
        if res.get("status") != "success":
            err = _format_provider_error("flutterwave", res, "Flutterwave payment initialization failed.", callback_url=callback_url)
            return {"success": False, "error": err}
        data = res.get("data", {})
        checkout_url = data.get("link", "")
        if not checkout_url:
            return {"success": False, "error": "Flutterwave did not return a checkout link."}
        return {
            "success": True,
            "checkout_url": checkout_url,
            "reference": tx_ref,
            "provider": "flutterwave",
        }

    elif gateway_provider == "paystack":
        amount_minor = _to_minor_units(bundle.price, bundle.currency)
        payload = {
            "amount": amount_minor,
            "email": customer_email,
            "reference": tx_ref,
            "currency": bundle.currency,
            "callback_url": callback_url,
            "metadata": {
                "session_token": session.session_token,
                "bundle_slug": bundle.slug,
                "cancel_url": cancel_url,
                "source": "onboarding_pre_tenant",
            },
        }
        res = _json_request(
            "POST",
            "https://api.paystack.co/transaction/initialize",
            headers={"Authorization": f"Bearer {secret_key}"},
            json_body=payload,
        )
        if not res.get("status"):
            err = _format_provider_error("paystack", res, "Paystack payment initialization failed.", callback_url=callback_url)
            return {"success": False, "error": err}
        data = res.get("data", {})
        checkout_url = data.get("authorization_url", "")
        if not checkout_url:
            return {"success": False, "error": "Paystack did not return an authorization URL."}
        return {
            "success": True,
            "checkout_url": checkout_url,
            "reference": data.get("reference", tx_ref),
            "access_code": data.get("access_code", ""),
            "provider": "paystack",
        }

    elif gateway_provider in {"manual", "cod"}:
        return {
            "success": True,
            "checkout_url": callback_url + ("&" if "?" in callback_url else "?") + "status=success",
            "reference": tx_ref,
            "provider": gateway_provider,
        }

    return {"success": False, "error": f"Unsupported platform gateway '{gateway_provider}'."}


def _verify_pre_tenant_payment(
    *,
    gateway_provider: str,
    reference: str,
    payload: dict,
) -> tuple[bool, str, str, Decimal, str]:
    from system.system_pay.models import PaymentGatewayDefinition
    from dashboard.payments_tenant.services.provider_checkout import _json_request, _from_minor_units
    import urllib.parse

    gateway_def = PaymentGatewayDefinition.objects.filter(provider=gateway_provider, is_enabled=True).first()
    if not gateway_def:
        return False, reference, "", Decimal("0.00"), "NGN"

    cred = gateway_def.platform_credentials.filter(is_active=True).order_by("-priority", "-created_at").first()
    if not cred or not cred.secret_key:
        return False, reference, "", Decimal("0.00"), "NGN"

    secret_key = cred.secret_key.strip()

    if gateway_provider == "flutterwave":
        transaction_id = (
            payload.get("transaction_id")
            or payload.get("id")
            or (payload.get("data") or {}).get("id")
        )
        if not transaction_id:
            return False, reference, "", Decimal("0.00"), "NGN"
        res = _json_request(
            "GET",
            f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify",
            headers={"Authorization": f"Bearer {secret_key}"},
        )
        if res.get("status") == "success":
            data = res.get("data", {})
            paid = data.get("status") == "successful"
            gw_ref = data.get("tx_ref", reference)
            gw_tx_id = str(data.get("id", transaction_id))
            amount = Decimal(str(data.get("amount", "0.00")))
            currency = data.get("currency", "NGN")
            return paid, gw_ref, gw_tx_id, amount, currency
        return False, reference, str(transaction_id), Decimal("0.00"), "NGN"

    elif gateway_provider == "paystack":
        ref = payload.get("reference") or payload.get("trxref") or reference
        if not ref:
            return False, reference, "", Decimal("0.00"), "NGN"
        res = _json_request(
            "GET",
            f"https://api.paystack.co/transaction/verify/{urllib.parse.quote(str(ref))}",
            headers={"Authorization": f"Bearer {secret_key}"},
        )
        if res.get("status"):
            data = res.get("data", {})
            paid = data.get("status") == "success"
            gw_ref = data.get("reference", str(ref))
            gw_tx_id = str(data.get("id", ""))
            amount = _from_minor_units(data.get("amount", 0), data.get("currency") or "NGN")
            currency = data.get("currency") or "NGN"
            return paid, gw_ref, gw_tx_id, amount, currency
        return False, reference, "", Decimal("0.00"), "NGN"

    elif gateway_provider in {"manual", "cod"}:
        return True, reference, reference, Decimal("0.00"), "NGN"

    return False, reference, "", Decimal("0.00"), "NGN"


def _grant_onboarding_bundle(bundle_slug: str):
    bundle = get_plan_bundle_by_slug(bundle_slug)
    if not bundle:
        return
    for item in bundle.items.select_related("feature").order_by("sort_order"):
        grant_manual_entitlement(
            feature=item.feature,
            quantity=item.quantity_override or 1,
            note="Granted during platform onboarding.",
            billing_cycle=bundle.billing_cycle,
            currency=bundle.currency,
        )


def _grant_onboarding_addons(feature_codes: list[str], currency: str = "NGN"):
    feature_map = {feature.code: feature for feature in get_active_feature_catalog(currency=currency, purchasable_only=True)}
    for code in feature_codes:
        feature = feature_map.get(code)
        if not feature:
            continue
        price = FeaturePrice.objects.filter(feature=feature, currency=currency, is_active=True).order_by("amount").first()
        quantity = 1
        if price and feature.feature_type == FeatureType.LIMIT:
            quantity = price.limit_increment or feature.default_limit_value or 1
        elif price and feature.feature_type == FeatureType.USAGE:
            quantity = price.credits_included or feature.default_usage_value or 1
        grant_manual_entitlement(
            feature=feature,
            quantity=quantity,
            note="Granted during platform onboarding.",
            billing_cycle=price.billing_cycle if price else "perpetual",
            currency=currency,
        )


def _get_post_auth_redirect_url(user, request=None) -> str:
    """
    Determines the appropriate landing page for a user after authentication or onboarding:
    - Superusers / Platform Staff -> /platform/dashboard/
    - Merchants with an existing store -> /dashboard/<schema_name>/
    - Users with incomplete onboarding -> Resume onboarding step
    - New users with no store -> /platform/register/
    """
    if not user or not getattr(user, "is_authenticated", False):
        return reverse("platform:login")

    if user.is_superuser or user.is_staff or getattr(user, "is_platform_admin", False):
        return reverse("platform:dashboard")

    # Incomplete onboarding
    try:
        resume_session = (
            OnboardingSession.objects.filter(email__iexact=user.email)
            .exclude(status__in=[OnboardingSession.Status.COMPLETED, OnboardingSession.Status.CANCELLED])
            .order_by("-updated_at")
            .first()
        )
        if resume_session:
            return _resume_onboarding_url(resume_session)
    except Exception:
        pass

    # Owned store
    try:
        shop = user.owned_shops.order_by("-created_on").first() if hasattr(user, "owned_shops") else None
        if shop:
            return reverse("dashboard:dashboard_home:home", kwargs={"prefix": shop.schema_name})
    except Exception:
        pass

    return reverse("platform:register")


def onboarding_start(request):
    if request.user.is_authenticated:
        existing_session = _get_existing_onboarding_session(request)
        if existing_session:
            return redirect(_resume_onboarding_url(existing_session))
        return redirect(_get_post_auth_redirect_url(request.user, request))
    session = _get_or_create_onboarding_session(request)
    _remember_requested_plan(request, session)
    context = _onboarding_context(
        request,
        session=session,
        page_title="Start Onboarding",
        current_step="start",
    )
    return render(request, "account/onboarding/start.html", context)


def onboarding_account(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect(_get_post_auth_redirect_url(request.user, request))
    session = existing_session or _get_or_create_onboarding_session(request)
    initial = {
        "email": session.email,
        "first_name": session.first_name,
        "last_name": session.last_name,
        "business_name": session.business_name,
    }
    form = OnboardingAccountForm(
        request.POST or None,
        initial=initial,
        existing_email=getattr(request.user, "email", ""),
    )
    if request.method == "POST" and form.is_valid():
        session.email = form.cleaned_data["email"]
        session.first_name = form.cleaned_data["first_name"]
        session.last_name = form.cleaned_data["last_name"]
        session.business_name = form.cleaned_data["business_name"]
        session.metadata = {
            **(session.metadata or {}),
            "password_hash": make_password(form.cleaned_data["password1"]),
        }
        session.save(update_fields=["email", "first_name", "last_name", "business_name", "metadata", "updated_at"])

        user = PlatformUser.objects.filter(email__iexact=session.email).first()
        if user is None:
            user = PlatformUser.objects.create(
                email=session.email,
                first_name=session.first_name,
                last_name=session.last_name,
                password=session.metadata["password_hash"],
                account_status=PlatformUser.AccountStatus.PENDING,
                is_verified=False,
            )
        else:
            dirty_fields = []
            if session.first_name and user.first_name != session.first_name:
                user.first_name = session.first_name
                dirty_fields.append("first_name")
            if session.last_name and user.last_name != session.last_name:
                user.last_name = session.last_name
                dirty_fields.append("last_name")
            if user.account_status != PlatformUser.AccountStatus.PENDING:
                user.account_status = PlatformUser.AccountStatus.PENDING
                dirty_fields.append("account_status")
            if dirty_fields:
                dirty_fields.append("updated_at")
                user.save(update_fields=dirty_fields)

        session.metadata = {
            **(session.metadata or {}),
            "platform_user_id": str(user.id),
        }
        session.save(update_fields=["metadata", "updated_at"])
        return redirect("platform:onboarding_plan")
    context = _onboarding_context(
        request,
        session=session,
        page_title="Create Account",
        current_step="account",
        form=form,
    )
    return render(request, "account/onboarding/account.html", context)


def onboarding_plan(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect(_get_post_auth_redirect_url(request.user, request))
    session = existing_session or _get_or_create_onboarding_session(request)
    requested_plan = _remember_requested_plan(request, session)
    if not session.email or not (session.metadata or {}).get("password_hash"):
        messages.info(request, "Tell us about your business before selecting a plan.")
        return redirect("platform:onboarding_account")
    plan_groups = get_plan_groups(currency=session.currency, current_only=True)
    plan_bundles = get_plan_bundles(currency=session.currency, current_only=True)
    default_plan_slug = (
        session.selected_bundle_slug
        or requested_plan
        or (session.metadata or {}).get("requested_plan_slug", "")
        or next((group["default_bundle"].slug for group in plan_groups if group["is_featured"]), "")
        or (plan_bundles[0].slug if plan_bundles else "")
    )
    form = OnboardingPlanForm(
        request.POST or None,
        bundle_choices=_bundle_choices(session.currency),
        addon_choices=_addon_choices(session.currency),
        initial={
            "bundle_slug": default_plan_slug,
            "addon_feature_codes": [],
        },
    )
    if request.method == "POST" and form.is_valid():
        session.selected_bundle_slug = form.cleaned_data["bundle_slug"]
        session.selected_feature_codes = []
        session.estimated_total = _estimate_onboarding_total(
            bundle_slug=session.selected_bundle_slug,
            addon_codes=session.selected_feature_codes,
            currency=session.currency,
        )
        session.payment_status = OnboardingSession.PaymentStatus.PENDING
        session.status = OnboardingSession.Status.READY
        session.save(update_fields=["selected_bundle_slug", "selected_feature_codes", "estimated_total", "payment_status", "status", "updated_at"])
        return redirect("platform:onboarding_checkout")
    context = _onboarding_context(
        request,
        session=session,
        page_title="Choose Plan",
        current_step="plan",
        form=form,
        bundles=plan_bundles,
        plan_groups=plan_groups,
        addons=[],
    )
    return render(request, "account/onboarding/plan.html", context)


def onboarding_checkout(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect(_get_post_auth_redirect_url(request.user, request))
    session = existing_session or _get_or_create_onboarding_session(request)
    if not session.selected_bundle_slug:
        messages.info(request, "Choose a plan before heading to payment.")
        return redirect("platform:onboarding_plan")
    if session.payment_status == OnboardingSession.PaymentStatus.PAID:
        return redirect("platform:onboarding_subdomain")

    selected_bundle = get_plan_bundle_by_slug(session.selected_bundle_slug, currency=session.currency)
    if not selected_bundle:
        messages.error(request, "The selected plan could not be found. Please choose a plan.")
        return redirect("platform:onboarding_plan")

    gateway_choices = _gateway_choices(session.currency)
    gateway_cards = _sorted_marketplace_gateways(session.currency)
    default_gateway_provider = (session.metadata or {}).get("selected_gateway_provider", "")
    if not default_gateway_provider and gateway_cards:
        default_gateway_provider = gateway_cards[0]["provider"]
    form = OnboardingCheckoutForm(
        request.POST or None,
        gateway_choices=gateway_choices,
        initial={"gateway_provider": default_gateway_provider},
    )

    if request.method == "POST":
        if not gateway_choices:
            messages.error(request, "No platform billing gateways are configured for onboarding yet.")
        elif form.is_valid():
            provider = form.cleaned_data["gateway_provider"]
            selected_gateway = _selected_gateway(session.currency, provider)
            metadata = dict(session.metadata or {})
            metadata["selected_gateway_provider"] = provider
            metadata["selected_gateway_name"] = selected_gateway["name"] if selected_gateway else provider.title()
            metadata["checkout_reference"] = metadata.get("checkout_reference") or _ensure_onboarding_checkout_reference(session)

            callback_base = reverse("platform:onboarding_payment_callback", kwargs={"purchase_reference": "PURCHASE_REFERENCE"})
            success_redirect_url = request.build_absolute_uri(f"{callback_base}?session_token={session.session_token}&status=success")
            cancel_redirect_url = request.build_absolute_uri(f"{callback_base}?session_token={session.session_token}&status=cancel")

            init_res = _init_pre_tenant_payment(
                gateway_provider=provider,
                bundle=selected_bundle,
                session=session,
                callback_url=success_redirect_url.replace("PURCHASE_REFERENCE", "pending"),
                cancel_url=cancel_redirect_url.replace("PURCHASE_REFERENCE", "pending"),
            )

            if not init_res.get("success"):
                messages.error(request, init_res.get("error", "Payment initialization failed."))
                return redirect("platform:onboarding_checkout")

            ref = init_res.get("reference", "")
            checkout_url = init_res.get("checkout_url", "")
            metadata["purchase_reference"] = ref
            metadata["provider_checkout_url"] = checkout_url
            session.metadata = metadata
            session.payment_status = OnboardingSession.PaymentStatus.PENDING
            session.save(update_fields=["metadata", "payment_status", "updated_at"])

            if not checkout_url:
                messages.error(request, "The selected gateway did not return a hosted checkout link. Please check your gateway credentials.")
                return redirect("platform:onboarding_checkout")
            return redirect(checkout_url)

    context = _onboarding_context(
        request,
        session=session,
        page_title="Complete Payment",
        current_step="checkout",
        selected_bundle=selected_bundle,
        selected_addons=[],
        gateway_cards=gateway_cards,
        form=form,
    )
    return render(request, "account/onboarding/checkout.html", context)


def onboarding_payment_session(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect(_get_post_auth_redirect_url(request.user, request))
    session = existing_session or _get_or_create_onboarding_session(request)
    if not session.selected_bundle_slug:
        messages.info(request, "Choose a plan before opening payment.")
        return redirect("platform:onboarding_plan")
    if session.payment_status == OnboardingSession.PaymentStatus.PAID:
        return redirect("platform:onboarding_subdomain")

    metadata = dict(session.metadata or {})
    provider = metadata.get("selected_gateway_provider", "")
    gateway = _selected_gateway(session.currency, provider)
    purchase_reference = metadata.get("purchase_reference", "")
    provider_checkout_url = metadata.get("provider_checkout_url", "")

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "retry":
            return redirect("platform:onboarding_checkout")
        if action == "cancel":
            metadata["payment_cancelled_at"] = timezone.now().isoformat()
            session.metadata = metadata
            session.payment_status = OnboardingSession.PaymentStatus.FAILED
            session.save(update_fields=["metadata", "payment_status", "updated_at"])
            messages.info(request, "Payment was cancelled. You can try again whenever you're ready.")
            return redirect("platform:onboarding_checkout")

    checkout_reference = metadata.get("checkout_reference") or _ensure_onboarding_checkout_reference(session)
    selected_bundle = get_plan_bundle_by_slug(session.selected_bundle_slug, currency=session.currency)

    context = _onboarding_context(
        request,
        session=session,
        page_title="Hosted Payment",
        current_step="checkout",
        selected_bundle=selected_bundle,
        selected_addons=[],
        selected_gateway=gateway,
        checkout_reference=checkout_reference,
        purchase_reference=purchase_reference,
        provider_checkout_url=provider_checkout_url,
    )
    return render(request, "account/onboarding/payment_session.html", context)


def onboarding_payment_callback(request, purchase_reference):
    session_token = (request.GET.get("session_token") or "").strip()
    status = (request.GET.get("status") or "").strip().lower()

    if not session_token:
        messages.error(request, "Invalid payment callback.")
        return redirect("platform:register")

    session = OnboardingSession.objects.filter(session_token=session_token).first()
    if not session:
        messages.error(request, "Onboarding session not found.")
        return redirect("platform:register")

    metadata = dict(session.metadata or {})
    provider = metadata.get("selected_gateway_provider", "flutterwave")
    ref = metadata.get("purchase_reference") or purchase_reference

    payload = request.POST.dict() if request.content_type and "application/json" not in request.content_type else {}
    try:
        import json
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    payload = {**payload, **request.GET.dict()}

    is_paid, gw_ref, gw_tx_id, amount, currency = _verify_pre_tenant_payment(
        gateway_provider=provider,
        reference=ref,
        payload=payload,
    )

    if not is_paid and status in {"success", "successful", "completed", "paid"}:
        is_paid = True
        gw_ref = gw_ref or ref

    if is_paid:
        session.payment_status = OnboardingSession.PaymentStatus.PAID
        metadata["payment_reference"] = gw_ref or ref
        metadata["gateway_reference"] = gw_ref or ref
        metadata["gateway_transaction_id"] = gw_tx_id
        metadata["paid_at"] = timezone.now().isoformat()
        session.metadata = metadata
        session.save(update_fields=["payment_status", "metadata", "updated_at"])
        messages.success(request, "Payment confirmed! Choose your store address to complete setup.")
        return redirect("platform:onboarding_subdomain")
    else:
        session.payment_status = OnboardingSession.PaymentStatus.FAILED
        session.save(update_fields=["payment_status", "updated_at"])
        messages.error(request, "Payment was not successful or was cancelled. Please try again.")
        return redirect("platform:onboarding_checkout")


def onboarding_subdomain(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect(_get_post_auth_redirect_url(request.user, request))
    session = existing_session or _get_or_create_onboarding_session(request)
    if not session.selected_bundle_slug:
        messages.info(request, "Choose a plan before reserving your subdomain.")
        return redirect("platform:onboarding_plan")
    if session.payment_status != OnboardingSession.PaymentStatus.PAID:
        messages.info(request, "Please complete payment before reserving your subdomain.")
        return redirect("platform:onboarding_checkout")

    existing_schema = (session.metadata or {}).get("tenant_schema_name")
    existing_domain = (session.metadata or {}).get("tenant_domain")

    form = OnboardingSubdomainForm(
        request.POST or None,
        initial={"desired_subdomain": session.desired_subdomain or existing_domain or ""},
    )
    if request.method == "POST" and form.is_valid():
        subdomain = form.cleaned_data["desired_subdomain"]
        if not TenantService.is_subdomain_available(subdomain):
            form.add_error("desired_subdomain", "That subdomain is already taken.")
        else:
            session.desired_subdomain = subdomain
            try:
                user = None
                platform_user_id = (session.metadata or {}).get("platform_user_id")
                if platform_user_id:
                    user = PlatformUser.objects.filter(id=platform_user_id).first()
                if user is None and session.email:
                    user = PlatformUser.objects.filter(email__iexact=session.email).first()

                if user is None:
                    user = PlatformUser.objects.create(
                        email=session.email,
                        first_name=session.first_name,
                        last_name=session.last_name,
                        password=(session.metadata or {}).get("password_hash", ""),
                        account_status=PlatformUser.AccountStatus.ACTIVE,
                        is_verified=False,
                    )
                else:
                    if user.account_status != PlatformUser.AccountStatus.ACTIVE:
                        user.account_status = PlatformUser.AccountStatus.ACTIVE
                        user.save(update_fields=["account_status"])

                session.metadata = {
                    **(session.metadata or {}),
                    "platform_user_id": str(user.id),
                }

                if not existing_schema:
                    schema_name = f"onboard_{uuid.uuid4().hex[:8]}"
                    shop, domain = TenantService.create_tenant(
                        owner=user,
                        name=session.business_name or f"{user.first_name}'s Store",
                        subdomain=subdomain,
                        schema_name=schema_name,
                        session=session,
                    )
                    existing_schema = shop.schema_name
                else:
                    try:
                        shop = Shop.objects.get(schema_name=existing_schema)
                        shop.owner = user
                        shop.name = session.business_name or shop.name
                        shop.save(update_fields=["owner", "name"])
                        Domain.objects.filter(tenant=shop, is_primary=True).update(domain=subdomain)
                        # Celery-free: remaining migrations are applied lazily in
                        # micro-chunks by the provisioning poll endpoint and the
                        # login guard middleware — nothing runs in this request.
                    except Shop.DoesNotExist:
                        schema_name = f"onboard_{uuid.uuid4().hex[:8]}"
                        shop, domain = TenantService.create_tenant(
                            owner=user,
                            name=session.business_name or f"{user.first_name}'s Store",
                            subdomain=subdomain,
                            schema_name=schema_name,
                            session=session,
                        )
                        existing_schema = shop.schema_name

                session.metadata = {
                    **(session.metadata or {}),
                    "tenant_schema_name": existing_schema,
                    "tenant_domain": subdomain,
                }
                session.status = OnboardingSession.Status.READY
                session.save(update_fields=["desired_subdomain", "metadata", "status", "updated_at"])

                login(request, user, backend=SCHEMA_AWARE_BACKEND)
                request.session["platform_onboarding_token"] = session.session_token
                request.session.modified = True
                return redirect("platform:onboarding_provisioning")

            except TenantCreationError as e:
                form.add_error("desired_subdomain", str(e))
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Subdomain setup error: %s", e)
                messages.error(request, f"An error occurred while setting up your store: {str(e)}")

    context = _onboarding_context(
        request,
        session=session,
        page_title="Reserve Subdomain",
        current_step="subdomain",
        form=form,
    )
    return render(request, "account/onboarding/subdomain.html", context)


def onboarding_provisioning(request):
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute('SET search_path = "public";')
    except Exception:
        pass
    connection.set_schema_to_public()

    # Allow both signup-flow (session) and login-flow (?schema=) to use this page
    schema_from_param = request.GET.get("schema", "").strip().lower()
    next_url = request.GET.get("next", "")

    existing_session = _get_existing_onboarding_session(request)
    session = existing_session or _get_or_create_onboarding_session(request)
    schema_name = schema_from_param or (session.metadata or {}).get("tenant_schema_name")

    # Try finding schema from authenticated user's shop
    if not schema_name and getattr(request.user, "is_authenticated", False):
        shop = Shop.objects.filter(owner=request.user).order_by("-created_on").first()
        if shop:
            schema_name = shop.schema_name
            session.metadata = {**(session.metadata or {}), "tenant_schema_name": schema_name}
            try:
                session.save(update_fields=["metadata", "updated_at"])
            except Exception:
                pass

    # For login-flow users coming via middleware redirect: skip payment checks
    login_flow = bool(schema_from_param)

    if not login_flow:
        if not session.selected_bundle_slug and not schema_name:
            return redirect("platform:onboarding_plan")
        if session.payment_status != OnboardingSession.PaymentStatus.PAID and not schema_name:
            return redirect("platform:onboarding_checkout")

    if not schema_name:
        return redirect("platform:onboarding_subdomain")

    # Celery-free flow: no heavy work happens here. The status polling
    # endpoint below advances migrations in time-budgeted micro-chunks each
    # time the waiting screen polls it.

    selected_bundle = None
    if session.selected_bundle_slug:
        selected_bundle = get_plan_bundle_by_slug(session.selected_bundle_slug, currency=session.currency)

    context = {
        "session": session,
        "selected_bundle": selected_bundle,
        "platform_domain_suffix": _platform_domain_suffix(request),
        # Extra context for login-flow
        "schema_name": schema_name,
        "login_flow": login_flow,
        "next_url": next_url,
    }
    return render(request, "account/onboarding/provisioning.html", context)


def onboarding_provisioning_status(request):
    import logging
    from django.utils import timezone
    from datetime import timedelta
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute('SET search_path = "public";')
    except Exception:
        pass
    connection.set_schema_to_public()

    logger = logging.getLogger(__name__)

    # Accept ?schema= from login-flow (middleware redirect) OR from session (signup-flow)
    schema_from_param = request.GET.get("schema", "").strip().lower()

    existing_session = _get_existing_onboarding_session(request)
    session = existing_session or _get_or_create_onboarding_session(request)
    schema_name = schema_from_param or (session.metadata or {}).get("tenant_schema_name")

    if not schema_name and getattr(request.user, "is_authenticated", False):
        shop = Shop.objects.filter(owner=request.user).order_by("-created_on").first()
        if shop:
            schema_name = shop.schema_name

    if not schema_name:
        return JsonResponse({"status": "provisioning", "progress": 25})

    shop = Shop.objects.filter(schema_name=schema_name).first()
    if not shop:
        return JsonResponse({"status": "provisioning", "progress": 30})

    from system.account.sso import get_tenant_subdomain_redirect_url

    if shop.provisioning_status == Shop.ProvisioningStatus.READY:
        redirect_url = get_tenant_subdomain_redirect_url(shop, request=request, user=request.user)
        return JsonResponse({
            "status": "ready",
            "progress": 100,
            "redirect_url": redirect_url,
            "schema_name": schema_name,
        })

    # ── Dual-Engine Migration Runner (Celery + Silent Stall Watchdog + Local Fallback) ──
    from system.account.watchdog import execute_tenant_migrations_with_watchdog

    poll_budget = getattr(settings, "TENANT_PROVISIONING_POLL_BUDGET", 6)
    advance_result: dict = {}
    try:
        advance_result = execute_tenant_migrations_with_watchdog(
            schema_name,
            time_budget=poll_budget,
            session_id=str(session.id) if session else None,
            source="poll_endpoint",
        )
    except Exception as advance_err:
        logger.warning("[Provisioning] Dual-Engine chunked pass failed for '%s': %s", schema_name, advance_err)

    shop.refresh_from_db()

    if advance_result.get("is_ready"):
        redirect_url = get_tenant_subdomain_redirect_url(shop, request=request, user=request.user)
        return JsonResponse({
            "status": "ready",
            "progress": 100,
            "redirect_url": redirect_url,
            "schema_name": schema_name,
            "engine": advance_result.get("engine", "local"),
        })

    if advance_result.get("failed") or (
        shop.provisioning_status == Shop.ProvisioningStatus.FAILED and advance_result.get("cooldown")
    ):
        return JsonResponse({
            "status": "failed",
            "progress": 100,
            "error": (
                advance_result.get("error")
                or shop.provisioning_error
                or "Store setup encountered an issue. Please contact support."
            ),
            "schema_name": schema_name,
            "engine": advance_result.get("engine", "local"),
        })

    # ── Real Migration Status Inspection ──────────────────────────────────────
    from system.account.schema_inspector import get_tenant_migration_status
    mig_status = get_tenant_migration_status(schema_name, use_cache=False)

    if mig_status.get("is_ready") is True:
        if shop.provisioning_status != Shop.ProvisioningStatus.READY:
            shop.provisioning_status = Shop.ProvisioningStatus.READY
            shop.provisioned_at = timezone.now()
            shop.provisioning_error = ""
            shop.save(update_fields=["provisioning_status", "provisioned_at", "provisioning_error"])

        redirect_url = get_tenant_subdomain_redirect_url(shop, request=request, user=request.user)
        return JsonResponse({
            "status": "ready",
            "progress": 100,
            "redirect_url": redirect_url,
            "schema_name": schema_name,
            "applied_count": mig_status.get("total_migrations", 54),
            "total_migrations": mig_status.get("total_migrations", 54),
            "engine": advance_result.get("engine", "local"),
        })


    # Progress is calculated directly from applied migrations
    calc_progress = max(10, mig_status.get("progress_percent", 35))
    current_stage = mig_status.get("current_stage")

    # Extract current migration name from provisioning_error progress message
    # Format: "Stage N/8: Name (pct% — applied/total applied) ▶ app_label"
    current_migration = ""
    error_msg = shop.provisioning_error or ""
    if "▶" in error_msg:
        try:
            current_migration = error_msg.split("▶")[-1].strip()
        except Exception:
            pass

    system_health = None
    if advance_result.get("run") and advance_result["run"].get("system_health"):
        system_health = advance_result["run"]["system_health"]
    else:
        try:
            from system.account.throttler import default_throttler
            cpu, ram = default_throttler.get_metrics()
            system_health = {
                "cpu_percent": round(cpu, 1),
                "ram_percent": round(ram, 1),
                "status": default_throttler.assess_status(cpu, ram),
            }
        except Exception:
            pass

    return JsonResponse({
        "status": "in_progress" if shop.provisioning_status == Shop.ProvisioningStatus.IN_PROGRESS else "provisioning",
        "progress": calc_progress,
        "schema_name": schema_name,
        "stage": current_stage,
        "stage_message": error_msg.split("(")[0].strip() if error_msg else (current_stage.get("name") if current_stage else "Provisioning tables..."),
        "current_migration": current_migration,
        "applied_count": mig_status.get("applied_count", 0),
        "total_migrations": mig_status.get("total_migrations", 54),
        "system_health": system_health,
    })



def onboarding_review(request):
    return redirect("platform:onboarding_provisioning")


class RegisterView(View):
    """
    Platform user registration with lightweight tenant creation (Celery-free).

    On successful registration:
    1. Creates the PlatformUser
    2. Creates the tenant (Shop) in public schema with STATUS = PROVISIONING
       (only a cheap CREATE SCHEMA runs here — no migrations)
    3. Logs the user in and redirects to the setup waiting screen, which
       polls a lightweight status endpoint that advances migrations in
       time-budgeted micro-chunks until the tenant is ready.
    """

    template_name = 'account/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(_get_post_auth_redirect_url(request.user, request))
        form = PlatformRegistrationForm()
        return render(
            request,
            self.template_name,
            {
                'form': form,
                'platform_domain_suffix': _platform_domain_suffix(request),
            },
        )

    def post(self, request):
        form = PlatformRegistrationForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    'form': form,
                    'platform_domain_suffix': _platform_domain_suffix(request),
                },
            )

        subdomain = form.cleaned_data.get('tenant_subdomain', '').lower()
        if subdomain and not TenantService.is_subdomain_available(subdomain):
            form.add_error('tenant_subdomain',
                           "This subdomain is already taken. Please choose another.")
            return render(
                request,
                self.template_name,
                {
                    'form': form,
                    'platform_domain_suffix': _platform_domain_suffix(request),
                },
            )

        try:
            user = form.save(commit=False)
            user.save()

            shop, domain = TenantService.create_tenant(
                owner=user,
                name=form.cleaned_data.get('tenant_name', ''),
                subdomain=subdomain,
            )

            login(request, user, backend=SCHEMA_AWARE_BACKEND)

            messages.success(
                request, f"Welcome! Your store '{shop.name}' is being initialized.")
            # Setup waiting screen — polls readiness and advances migrations
            # lazily; no heavy work happens inside this registration request.
            return redirect("platform:onboarding_provisioning")

        except TenantCreationError as e:
            messages.error(request, str(e))
            form.add_error(None, str(e))
            return render(
                request,
                self.template_name,
                {
                    'form': form,
                    'platform_domain_suffix': _platform_domain_suffix(request),
                },
            )
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            form.add_error(None, f"An error occurred: {str(e)}")
            return render(
                request,
                self.template_name,
                {
                    'form': form,
                    'platform_domain_suffix': _platform_domain_suffix(request),
                },
            )


class LoginView(View):
    """
    Platform user login.
    """

    template_name = 'account/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(_get_post_auth_redirect_url(request.user, request))
        form = PlatformLoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = PlatformLoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        email = form.cleaned_data.get('email')
        password = form.cleaned_data.get('password')

        user = authenticate(
            request,
            username=email,
            password=password,
        )

        if user is not None:
            if not user.can_login:
                messages.error(request,
                               "Your account is not active. Please contact support.")
                form.add_error(None, "Your account is not active. Please contact support.")
                return render(request, self.template_name, {'form': form})

            login(request, user)

            # Handle remember me
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)  # Browser session only

            messages.success(
                request, f"Welcome back, {user.get_short_name()}!")

            resume_session = (
                OnboardingSession.objects.filter(email__iexact=user.email)
                .exclude(status__in=[OnboardingSession.Status.COMPLETED, OnboardingSession.Status.CANCELLED])
                .order_by("-updated_at")
                .first()
            )
            if resume_session:
                request.session["platform_onboarding_token"] = resume_session.session_token
                request.session.modified = True

            # Redirect to next parameter, onboarding resume, or user's target dashboard
            next_url = request.GET.get('next')
            if next_url and next_url != reverse('platform:dashboard'):
                return redirect(next_url)
            return redirect(_get_post_auth_redirect_url(user, request))
        else:
            messages.error(request,
                           "Invalid email or password. Please try again.")
            form.add_error(None, "Invalid email or password. Please try again.")
            return render(request, self.template_name, {'form': form})


class LogoutView(View):
    """
    Platform user logout.
    """

    def get(self, request):
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect('platform:login')


@rate_limit(rate=20, per_seconds=60, scope="platform_subdomain_check", by_user=False)
def check_subdomain(request):
    raw_subdomain = request.GET.get("subdomain", "")
    try:
        subdomain = _validate_subdomain_candidate(raw_subdomain)
    except ValidationError as exc:
        return JsonResponse(
            {
                "available": False,
                "subdomain": (raw_subdomain or "").strip().lower(),
                "message": exc.messages[0],
            },
            status=400,
        )

    is_available = TenantService.is_subdomain_available(subdomain)
    requested_domain = _formatted_store_domain(request, subdomain)
    return JsonResponse(
        {
            "available": is_available,
            "subdomain": subdomain,
            "message": (
                f"{requested_domain} is available."
                if is_available
                else f"{requested_domain} is already taken."
            ),
        }
    )


class PasswordResetRequestView(View):
    """
    Request a password reset email.
    """

    template_name = 'account/password_reset_request.html'

    def get(self, request):
        form = PlatformPasswordResetRequestForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = PlatformPasswordResetRequestForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        email = form.cleaned_data.get('email')
        try:
            user = PlatformUser.objects.get(email__iexact=email)
            # Create reset token and send email
            # TODO: Implement email sending
            token = user.password_reset_tokens.create_for_user(user)
            # send_password_reset_email(user, token)
        except PlatformUser.DoesNotExist:
            pass  # Don't reveal email existence

        # Always show success message
        messages.success(request,
                         "If an account with that email exists, "
                         "we have sent password reset instructions.")
        return redirect('platform:login')
