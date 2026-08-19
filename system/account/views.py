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
from dashboard.feature_marketplace.services import grant_manual_entitlement
from system.feature_marketplace.models import FeatureDefinition, FeaturePrice, FeatureType
from system.feature_marketplace.services import get_active_bundles, get_active_feature_catalog, get_marketplace_gateways

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
    if not session.desired_subdomain:
        return reverse("platform:onboarding_subdomain")
    return reverse("platform:onboarding_review")


def _onboarding_progress(current_step: str):
    steps = (
        ("start", "Welcome"),
        ("account", "Account"),
        ("plan", "Plan"),
        ("checkout", "Payment"),
        ("subdomain", "Subdomain"),
        ("review", "Launch"),
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
    for bundle in get_active_bundles(currency=currency, current_only=True):
        label = f"{bundle.name} ({bundle.currency} {bundle.price}/{bundle.billing_cycle})"
        choices.append((bundle.slug, label))
    return choices


def _addon_choices(currency: str = "NGN"):
    choices = []
    for feature in get_active_feature_catalog(currency=currency, purchasable_only=True):
        if not feature.prices.exists():
            continue
        first_price = feature.prices.first()
        choices.append((feature.code, f"{feature.name} ({first_price.currency} {first_price.amount}/{first_price.billing_cycle})"))
    return choices


def _estimate_onboarding_total(*, bundle_slug: str = "", addon_codes: list[str] | None = None, currency: str = "NGN") -> Decimal:
    addon_codes = addon_codes or []
    total = Decimal("0.00")
    bundle = next((item for item in get_active_bundles(currency=currency, current_only=True) if item.slug == bundle_slug), None)
    if bundle:
        total += bundle.price
    feature_map = {feature.code: feature for feature in get_active_feature_catalog(currency=currency, purchasable_only=True)}
    for code in addon_codes:
        feature = feature_map.get(code)
        if not feature or not feature.prices.exists():
            continue
        total += feature.prices.first().amount
    return total.quantize(Decimal("0.01"))


def _gateway_choices(currency: str = "NGN"):
    return [
        (gateway["provider"], f'{gateway["name"]} ({gateway["environment"]})')
        for gateway in get_marketplace_gateways(currency=currency)
    ]


def _selected_gateway(currency: str, provider: str):
    for gateway in get_marketplace_gateways(currency=currency):
        if gateway["provider"] == provider:
            return gateway
    return None


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


def _grant_onboarding_bundle(bundle_slug: str):
    bundle = next((item for item in get_active_bundles(current_only=True) if item.slug == bundle_slug), None)
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


def onboarding_start(request):
    if request.user.is_authenticated:
        existing_session = _get_existing_onboarding_session(request)
        if existing_session:
            return redirect(_resume_onboarding_url(existing_session))
        return redirect("platform:dashboard")
    session = _get_or_create_onboarding_session(request)
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
        return redirect("platform:dashboard")
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
        return redirect("platform:dashboard")
    session = existing_session or _get_or_create_onboarding_session(request)
    if not session.email or not (session.metadata or {}).get("password_hash"):
        messages.info(request, "Tell us about your business before selecting a plan.")
        return redirect("platform:onboarding_account")
    form = OnboardingPlanForm(
        request.POST or None,
        bundle_choices=_bundle_choices(session.currency),
        addon_choices=_addon_choices(session.currency),
        initial={
            "bundle_slug": session.selected_bundle_slug,
            "addon_feature_codes": session.selected_feature_codes,
        },
    )
    if request.method == "POST" and form.is_valid():
        session.selected_bundle_slug = form.cleaned_data["bundle_slug"]
        session.selected_feature_codes = form.cleaned_data["addon_feature_codes"]
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
        bundles=get_active_bundles(currency=session.currency, current_only=True),
        addons=get_active_feature_catalog(currency=session.currency, purchasable_only=True),
    )
    return render(request, "account/onboarding/plan.html", context)


def onboarding_checkout(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect("platform:dashboard")
    session = existing_session or _get_or_create_onboarding_session(request)
    if not session.selected_bundle_slug:
        messages.info(request, "Choose a starter plan before heading to payment.")
        return redirect("platform:onboarding_plan")
    if session.payment_status == OnboardingSession.PaymentStatus.PAID:
        return redirect("platform:onboarding_subdomain")

    selected_bundle = next((item for item in get_active_bundles(currency=session.currency, current_only=True) if item.slug == session.selected_bundle_slug), None)
    addon_map = {feature.code: feature for feature in get_active_feature_catalog(currency=session.currency, purchasable_only=True)}
    selected_addons = [addon_map[code] for code in session.selected_feature_codes if code in addon_map]
    gateway_choices = _gateway_choices(session.currency)
    form = OnboardingCheckoutForm(
        request.POST or None,
        gateway_choices=gateway_choices,
        initial={"gateway_provider": (session.metadata or {}).get("selected_gateway_provider", "")},
    )

    if request.method == "POST":
        if not gateway_choices:
            messages.error(request, "No platform billing gateways are configured for onboarding yet.")
        elif form.is_valid():
            selected_gateway = _selected_gateway(session.currency, form.cleaned_data["gateway_provider"])
            metadata = dict(session.metadata or {})
            metadata["selected_gateway_provider"] = form.cleaned_data["gateway_provider"]
            metadata["selected_gateway_name"] = selected_gateway["name"] if selected_gateway else form.cleaned_data["gateway_provider"]
            metadata["checkout_reference"] = metadata.get("checkout_reference") or _ensure_onboarding_checkout_reference(session)
            session.metadata = metadata
            session.payment_status = OnboardingSession.PaymentStatus.PENDING
            session.save(update_fields=["metadata", "payment_status", "updated_at"])
            return redirect("platform:onboarding_payment_session")

    context = _onboarding_context(
        request,
        session=session,
        page_title="Complete Payment",
        current_step="checkout",
        selected_bundle=selected_bundle,
        selected_addons=selected_addons,
        gateway_cards=get_marketplace_gateways(currency=session.currency),
        form=form,
    )
    return render(request, "account/onboarding/checkout.html", context)


def onboarding_payment_session(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect("platform:dashboard")
    session = existing_session or _get_or_create_onboarding_session(request)
    if not session.selected_bundle_slug:
        messages.info(request, "Choose a starter plan before opening payment.")
        return redirect("platform:onboarding_plan")
    if session.payment_status == OnboardingSession.PaymentStatus.PAID:
        return redirect("platform:onboarding_subdomain")

    metadata = dict(session.metadata or {})
    provider = metadata.get("selected_gateway_provider", "")
    gateway = _selected_gateway(session.currency, provider)
    if gateway is None:
        messages.info(request, "Choose a billing gateway before continuing.")
        return redirect("platform:onboarding_checkout")

    checkout_reference = metadata.get("checkout_reference") or _ensure_onboarding_checkout_reference(session)
    payment_reference = metadata.get("payment_reference", "")

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "confirm":
            payment_reference = payment_reference or _ensure_onboarding_payment_reference(session)
            metadata = dict(session.metadata or {})
            metadata["selected_gateway_provider"] = provider
            metadata["selected_gateway_name"] = gateway["name"]
            metadata["checkout_reference"] = checkout_reference
            metadata["payment_reference"] = payment_reference
            metadata["paid_at"] = timezone.now().isoformat()
            session.metadata = metadata
            session.payment_status = OnboardingSession.PaymentStatus.PAID
            session.save(update_fields=["metadata", "payment_status", "updated_at"])
            messages.success(request, "Payment confirmed. You can now reserve your subdomain.")
            return redirect("platform:onboarding_subdomain")
        if action == "cancel":
            metadata = dict(session.metadata or {})
            metadata["checkout_reference"] = checkout_reference
            metadata["payment_cancelled_at"] = timezone.now().isoformat()
            session.metadata = metadata
            session.payment_status = OnboardingSession.PaymentStatus.FAILED
            session.save(update_fields=["metadata", "payment_status", "updated_at"])
            messages.info(request, "Payment was cancelled. You can try again whenever you're ready.")
            return redirect("platform:onboarding_checkout")

    selected_bundle = next((item for item in get_active_bundles(currency=session.currency, current_only=True) if item.slug == session.selected_bundle_slug), None)
    addon_map = {feature.code: feature for feature in get_active_feature_catalog(currency=session.currency, purchasable_only=True)}
    selected_addons = [addon_map[code] for code in session.selected_feature_codes if code in addon_map]
    context = _onboarding_context(
        request,
        session=session,
        page_title="Hosted Payment",
        current_step="checkout",
        selected_bundle=selected_bundle,
        selected_addons=selected_addons,
        selected_gateway=gateway,
        checkout_reference=checkout_reference,
    )
    return render(request, "account/onboarding/payment_session.html", context)


def onboarding_subdomain(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect("platform:dashboard")
    session = existing_session or _get_or_create_onboarding_session(request)
    if not session.selected_bundle_slug:
        messages.info(request, "Choose a starter plan before reserving your subdomain.")
        return redirect("platform:onboarding_plan")
    if session.payment_status != OnboardingSession.PaymentStatus.PAID:
        messages.info(request, "Complete payment before reserving your store subdomain.")
        return redirect("platform:onboarding_checkout")
    form = OnboardingSubdomainForm(
        request.POST or None,
        initial={"desired_subdomain": session.desired_subdomain},
    )
    if request.method == "POST" and form.is_valid():
        subdomain = form.cleaned_data["desired_subdomain"]
        if not TenantService.is_subdomain_available(subdomain):
            form.add_error("desired_subdomain", "That subdomain is already taken.")
        else:
            session.desired_subdomain = subdomain
            session.save(update_fields=["desired_subdomain", "updated_at"])
            return redirect("platform:onboarding_review")
    context = _onboarding_context(
        request,
        session=session,
        page_title="Choose Subdomain",
        current_step="subdomain",
        form=form,
    )
    return render(request, "account/onboarding/subdomain.html", context)


def onboarding_review(request):
    existing_session = _get_existing_onboarding_session(request)
    if request.user.is_authenticated and existing_session is None:
        return redirect("platform:dashboard")
    session = existing_session or _get_or_create_onboarding_session(request)
    if not session.selected_bundle_slug:
        messages.info(request, "Choose a starter plan before launching your store.")
        return redirect("platform:onboarding_plan")
    if session.payment_status != OnboardingSession.PaymentStatus.PAID:
        messages.info(request, "Complete payment before launching your store.")
        return redirect("platform:onboarding_checkout")
    if not session.desired_subdomain:
        messages.info(request, "Reserve a subdomain before launching your store.")
        return redirect("platform:onboarding_subdomain")
    selected_bundle = next((item for item in get_active_bundles(currency=session.currency, current_only=True) if item.slug == session.selected_bundle_slug), None)
    addon_map = {feature.code: feature for feature in get_active_feature_catalog(currency=session.currency, purchasable_only=True)}
    selected_addons = [addon_map[code] for code in session.selected_feature_codes if code in addon_map]

    if request.method == "POST":
        if not all([session.email, session.business_name, session.desired_subdomain, session.metadata.get("password_hash")]):
            messages.error(request, "Complete the earlier onboarding steps before launching your store.")
            return redirect("platform:onboarding_account")
        try:
            with transaction.atomic():
                user = PlatformUser.objects.filter(email__iexact=session.email).first()
                if user is None:
                    user = PlatformUser.objects.create(
                        email=session.email,
                        first_name=session.first_name,
                        last_name=session.last_name,
                        password=session.metadata["password_hash"],
                        account_status=PlatformUser.AccountStatus.ACTIVE,
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
                    if user.account_status != PlatformUser.AccountStatus.ACTIVE:
                        user.account_status = PlatformUser.AccountStatus.ACTIVE
                        dirty_fields.append("account_status")
                    if dirty_fields:
                        dirty_fields.append("updated_at")
                        user.save(update_fields=dirty_fields)
                shop, domain = TenantService.create_tenant(
                    owner=user,
                    name=session.business_name,
                    subdomain=session.desired_subdomain,
                )
                with schema_context(shop.schema_name):
                    if session.selected_bundle_slug:
                        _grant_onboarding_bundle(session.selected_bundle_slug)
                    if session.selected_feature_codes:
                        _grant_onboarding_addons(session.selected_feature_codes, session.currency)
            session.status = OnboardingSession.Status.COMPLETED
            session.payment_status = OnboardingSession.PaymentStatus.PAID
            session.completed_at = timezone.now()
            session.save(update_fields=["status", "payment_status", "completed_at", "updated_at"])
            request.session.pop("platform_onboarding_token", None)
            request.session.modified = True
            login(request, user, backend=SCHEMA_AWARE_BACKEND)
            messages.success(request, f"Welcome to SABIStart. {shop.name} is ready.")
            return redirect("dashboard:dashboard_home:home", prefix=shop.schema_name)
        except TenantCreationError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, f"Unable to complete onboarding: {exc}")

    context = _onboarding_context(
        request,
        session=session,
        page_title="Review & Launch",
        current_step="review",
        selected_bundle=selected_bundle,
        selected_addons=selected_addons,
        selected_gateway_name=(session.metadata or {}).get("selected_gateway_name", ""),
        payment_reference=(session.metadata or {}).get("payment_reference", ""),
    )
    return render(request, "account/onboarding/review.html", context)


class RegisterView(View):
    """
    Platform user registration with automatic tenant creation.

    On successful registration:
    1. Creates the PlatformUser
    2. Creates the tenant (Shop) with the specified subdomain
    3. Creates the default Domain
    4. Logs the user in
    """

    template_name = 'account/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('platform:dashboard')
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

        # Check subdomain availability before creating user
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
            # Create the platform user
            user = form.save(commit=False)
            user.save()

            # Create the tenant (shop)
            shop, domain = TenantService.create_tenant(
                owner=user,
                name=form.cleaned_data.get('tenant_name', ''),
                subdomain=subdomain,
            )

            # Log the user in
            login(request, user, backend=SCHEMA_AWARE_BACKEND)

            # TODO: In production, trigger async task to run tenant migrations
            # For now, we'll skip migration during registration
            # TenantService.run_tenant_migrations(shop.schema_name)

            messages.success(
                request, f"Welcome! Your store '{shop.name}' has been created.")
            return redirect('platform:dashboard')

        except TenantCreationError as e:
            messages.error(request, str(e))
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
            return redirect('platform:dashboard')
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

            # Redirect to next parameter, onboarding resume, or dashboard
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            if resume_session:
                return redirect(_resume_onboarding_url(resume_session))
            return redirect('platform:dashboard')
        else:
            messages.error(request,
                           "Invalid email or password. Please try again.")
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
