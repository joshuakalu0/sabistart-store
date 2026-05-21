import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from dashboard.pricing.utiles.partners import build_partner_dashboard_bundle
from public.cart.models import Order
from public.product.models import Product, ProductReview
from public.storefront.forms import (
    AddressForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    ProfileForm,
    ReferralInviteForm,
    SecurityForm,
)
from public.storefront.services import (
    build_breadcrumbs,
    get_compare_products,
    get_customer_order_queryset,
    get_order_for_request,
    get_or_create_customer_profile,
    get_recently_viewed_products,
    get_wishlist_products,
    render_info_page,
    render_storefront,
    toggle_session_product,
)
from public.userauth.models import CustomerAddress, TenantEmailVerificationToken, TenantPasswordResetToken, TenantUser

logger = logging.getLogger(__name__)


def _account_shell(request, title, body):
    return render_info_page(
        request,
        title=title,
        body=body,
        extra_context={"breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), (title, ""))},
    )


def verify_email_view(request):
    token_value = request.GET.get("token", "")
    if token_value:
        token = TenantEmailVerificationToken.objects.filter(token=token_value, is_used=False).select_related("user").first()
        if token and token.consume():
            token.user.is_verified = True
            token.user.verified_at = timezone.now()
            token.user.account_status = TenantUser.AccountStatus.ACTIVE
            token.user.save(update_fields=["is_verified", "verified_at", "account_status", "updated_at"])
            messages.success(request, "Email verified.")
        else:
            messages.error(request, "That verification token is invalid or expired.")
        return redirect("tenant:verify_email")

    generated_token = None
    if request.method == "POST" and request.user.is_authenticated:
        generated_token = TenantEmailVerificationToken.create_for_user(request.user)
        messages.success(request, "A new verification token has been issued.")

    return render_storefront(
        request,
        "auth/verify_email.html",
        {
            "generated_token": generated_token,
            "verification_url": f"{request.build_absolute_uri(request.path)}?token={generated_token.token}" if generated_token else "",
        },
        page_title="Verify Email",
        page_description="Verify the current tenant account email address.",
    )


def password_reset_view(request):
    form = PasswordResetRequestForm(request.POST or None)
    reset_url = ""
    if request.method == "POST" and form.is_valid():
        user = TenantUser.objects.filter(email__iexact=form.cleaned_data["email"]).first()
        if user:
            token = TenantPasswordResetToken.create_for_user(user, request_ip=request.META.get("REMOTE_ADDR"))
            uid = urlsafe_base64_encode(force_bytes(str(user.pk)))
            reset_url = request.build_absolute_uri(
                f"/account/password-reset/confirm/{uid}/{token.token}/"
            )
        messages.success(request, "If the account exists, a password reset token has been created.")

    return render_storefront(
        request,
        "auth/password_reset.html",
        {"form": form, "reset_url": reset_url},
        page_title="Password Reset",
        page_description="Request a password reset token for this tenant account.",
    )


def password_reset_confirm_view(request, uidb64, token):
    form = PasswordResetConfirmForm(request.POST or None)
    user = None
    reset_token = None
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = TenantUser.objects.filter(pk=user_id).first()
    except Exception:
        user = None

    if user:
        reset_token = TenantPasswordResetToken.objects.filter(user=user, token=token, is_used=False).first()

    if request.method == "POST" and form.is_valid():
        if not user or not reset_token or not reset_token.consume():
            messages.error(request, "That reset token is invalid or expired.")
        else:
            user.set_password(form.cleaned_data["new_password1"])
            user.password_changed_at = timezone.now()
            user.force_password_reset = False
            user.save(update_fields=["password", "password_changed_at", "force_password_reset", "updated_at"])
            messages.success(request, "Password updated.")
            return redirect("tenant:login")

    return render_storefront(
        request,
        "auth/password_reset_confirm.html",
        {"form": form, "token_valid": bool(user and reset_token and reset_token.is_valid)},
        page_title="Confirm Password Reset",
        page_description="Set a new password for the tenant account.",
    )


@login_required(login_url="tenant:login")
def account_overview_view(request):
    orders = get_customer_order_queryset(request)
    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "")),
        "recent_orders": orders[:5],
        "metrics": {
            "total_orders": orders.count(),
            "wishlist_count": len(get_wishlist_products(request)),
            "recently_viewed_count": len(get_recently_viewed_products(request)),
            "compare_count": len(get_compare_products(request)),
        },
    }
    return render_storefront(request, "account/dashboard.html", context, page_title="Account Overview")


@login_required(login_url="tenant:login")
def account_orders_view(request):
    orders = get_customer_order_queryset(request)
    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Orders", "")),
        "orders": orders,
    }
    return render_storefront(request, "account/orders.html", context, page_title="My Orders")


@login_required(login_url="tenant:login")
def account_order_detail_view(request, order_id):
    order = get_order_for_request(request, order_id)
    if order is None:
        messages.error(request, "Order not found.")
        return redirect("tenant:account_orders")
    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Orders", "/account/orders/"), (order.order_number, "")),
        "order": order,
    }
    return render_storefront(request, "account/order_detail.html", context, page_title=order.order_number)


@login_required(login_url="tenant:login")
def order_tracking_view(request, order_id):
    order = get_order_for_request(request, order_id)
    if order is None:
        messages.error(request, "Order not found.")
        return redirect("tenant:account_orders")
    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Orders", "/account/orders/"), ("Tracking", "")),
        "order": order,
        "tracking_mode": True,
    }
    return render_storefront(request, "account/order_detail.html", context, page_title=f"Track {order.order_number}")


@login_required(login_url="tenant:login")
def order_return_view(request, order_id):
    order = get_order_for_request(request, order_id)
    if order is None:
        messages.error(request, "Order not found.")
        return redirect("tenant:account_orders")
    return _account_shell(request, "Returns", f"Returns for {order.order_number} are shown as a storefront shell until the returns workflow is connected.")


@login_required(login_url="tenant:login")
def profile_edit_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("tenant:profile_edit")
    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Profile", "")),
        "form": form,
    }
    return render_storefront(request, "account/profile.html", context, page_title="Profile")


@login_required(login_url="tenant:login")
def account_security_view(request):
    form = SecurityForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not request.user.check_password(form.cleaned_data["current_password"]):
            messages.error(request, "Current password is incorrect.")
        else:
            request.user.set_password(form.cleaned_data["new_password1"])
            request.user.password_changed_at = timezone.now()
            request.user.save(update_fields=["password", "password_changed_at", "updated_at"])
            messages.success(request, "Password updated.")
            return redirect("tenant:login")
    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Security", "")),
        "form": form,
    }
    return render_storefront(request, "account/security.html", context, page_title="Security")


@login_required(login_url="tenant:login")
def address_book_view(request):
    customer = get_or_create_customer_profile(request.user)
    address = None
    if request.GET.get("edit"):
        address = get_object_or_404(CustomerAddress, pk=request.GET["edit"], customer=customer)

    if request.method == "POST" and request.POST.get("action") == "delete":
        CustomerAddress.objects.filter(pk=request.POST.get("address_id"), customer=customer).delete()
        messages.success(request, "Address removed.")
        return redirect("tenant:address_book")

    form = AddressForm(request.POST or None, instance=address)
    if request.method == "POST" and request.POST.get("action") != "delete" and form.is_valid():
        saved_address = form.save(commit=False)
        saved_address.customer = customer
        saved_address.save()
        messages.success(request, "Address saved.")
        return redirect("tenant:address_book")

    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Addresses", "")),
        "form": form,
        "addresses": customer.addresses.filter(is_active=True).order_by("-is_default_shipping", "-created_at"),
    }
    return render_storefront(request, "account/addresses.html", context, page_title="Address Book")


def payment_methods_view(request):
    return _account_shell(request, "Payment Methods", "Saved payment methods are intentionally presented as a shell until a payment vault is selected.")


def wishlist_view(request):
    if request.method == "POST":
        product_id = request.POST.get("product_id")
        if product_id:
            added = toggle_session_product(request, "wishlist", product_id)
            messages.success(request, "Saved to wishlist." if added else "Removed from wishlist.")
        return redirect("tenant:wishlist")

    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Wishlist", "")),
        "products": get_wishlist_products(request),
    }
    return render_storefront(request, "account/wishlist.html", context, page_title="Wishlist")


def recently_viewed_view(request):
    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Recently Viewed", "")),
        "products": get_recently_viewed_products(request),
    }
    return render_storefront(request, "account/recently_viewed.html", context, page_title="Recently Viewed")


def loyalty_portal_view(request):
    return _account_shell(request, "Loyalty", "Loyalty program details can be connected later without changing this tenant-facing route.")


@login_required(login_url="tenant:login")
def referral_dashboard_view(request):
    customer = get_or_create_customer_profile(request.user)
    dashboard_bundle = build_partner_dashboard_bundle(request, customer)
    invite_form = ReferralInviteForm(request.POST or None)
    if request.method == "POST" and invite_form.is_valid():
        messages.success(
            request,
            f"Referral invite prepared for {invite_form.cleaned_data['email']}. Share link: {dashboard_bundle['share']['share_url']}"
            if dashboard_bundle.get("share")
            else "Referral invite prepared.",
        )
        return redirect("tenant:referral_dashboard")

    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Referrals", "")),
        "invite_form": invite_form,
        "referral_bundle": dashboard_bundle,
    }
    return render_storefront(request, "account/referrals.html", context, page_title="Referrals")


def store_credit_view(request):
    return _account_shell(request, "Store Credit", "Store credit balances are not persisted in this pass, but the account shell is ready.")


def user_subscriptions_view(request):
    return _account_shell(request, "Subscriptions", "Subscription management is represented as a storefront shell until subscription billing is added.")


def notification_settings_view(request):
    return _account_shell(request, "Notifications", "Notification preferences are presented as a tenant-themed shell for now.")


def privacy_settings_view(request):
    return _account_shell(request, "Privacy", "Privacy tools are shown here and can be connected to consent workflows later.")


def account_delete_view(request):
    return _account_shell(request, "Delete Account", "Self-service account deletion is intentionally disabled in this implementation.")


@login_required(login_url="tenant:login")
def user_reviews_view(request):
    customer = get_or_create_customer_profile(request.user)
    reviews = (
        ProductReview.objects.select_related("product")
        .filter(customer=customer)
        .order_by("-created_at")
    )
    context = {
        "breadcrumbs": build_breadcrumbs(("Account", "/account/dashboard/"), ("Reviews", "")),
        "reviews": reviews,
    }
    return render_storefront(request, "account/reviews.html", context, page_title="Reviews")
