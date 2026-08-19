"""
Tenant storefront authentication views.
"""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect

from public.storefront.services import get_or_create_cart, render_storefront
from public.userauth.forms import TenantLoginForm, TenantRegistrationForm
from public.userauth.models import Customer, TenantEmailVerificationToken

SCHEMA_AWARE_BACKEND = "sabistart.auth_backends.SchemaAwareAuthenticationBackend"


def tenant_register_view(request):
    if request.user.is_authenticated:
        return redirect("tenant:account_overview")

    form = TenantRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        Customer.objects.get_or_create(user=user, defaults={"status": Customer.Status.ACTIVE})
        TenantEmailVerificationToken.create_for_user(user)
        login(request, user, backend=SCHEMA_AWARE_BACKEND)
        get_or_create_cart(request)
        messages.success(request, "Your account has been created. A verification token was issued for this tenant.")
        return redirect("tenant:account_overview")

    return render_storefront(
        request,
        "auth/register.html",
        {"form": form},
        page_title="Create Account",
        page_description="Create a tenant-scoped customer account for this storefront.",
    )


def tenant_login_view(request):
    if request.user.is_authenticated:
        return redirect("tenant:account_overview")

    form = TenantLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        
        user = authenticate(
            request,
            username=email,
            password=password,
        )

        if user is None:
            messages.error(request, "Invalid email or password.")
        else:
            if not user.can_login:
                messages.error(request, "Your account is not allowed to log in at the moment.")
            else:
                login(request, user)
                if not form.cleaned_data.get("remember_me"):
                    request.session.set_expiry(0)
                get_or_create_cart(request)
                messages.success(request, f"Welcome back, {user.get_short_name()}.")
                next_url = request.GET.get("next") or request.POST.get("next")
                return redirect(next_url or "tenant:account_overview")

    return render_storefront(
        request,
        "auth/login.html",
        {"form": form, "next_url": request.GET.get("next", "")},
        page_title="Sign In",
        page_description="Access your storefront account and checkout history.",
    )


def tenant_logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("tenant:login")


def tenant_account_view(request):
    return redirect("tenant:account_overview")
