import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from public.cart.models import Order, OrderAddress
from public.storefront.forms import (
    CheckoutContactForm,
    GuestCheckoutForm,
    PaymentMethodForm,
    ShippingMethodForm,
)
from public.storefront.services import (
    build_breadcrumbs,
    clear_checkout_state,
    create_order_from_checkout,
    get_cart_summary,
    get_checkout_prefill,
    get_checkout_settings_cached,
    get_checkout_state,
    get_order_for_request,
    get_or_create_cart,
    get_payment_methods,
    get_shipping_methods,
    render_storefront,
    update_checkout_state,
    update_order_payment_state,
)


def checkout_auth_view(request):
    cart = get_or_create_cart(request)
    if cart.is_empty:
        messages.error(request, "Your cart is empty.")
        return redirect("cart:cart_page")

    checkout_settings = get_checkout_settings_cached(request)
    if request.user.is_authenticated:
        update_checkout_state(request, email=request.user.email)
        return redirect("checkout:checkout_info")

    allow_guest_checkout = bool(getattr(checkout_settings, "allow_guest_checkout", True))
    form = GuestCheckoutForm(request.POST or None)
    if request.method == "POST" and allow_guest_checkout and form.is_valid():
        update_checkout_state(request, email=form.cleaned_data["email"])
        cart.email = form.cleaned_data["email"]
        cart.save(update_fields=["email", "updated_at"])
        return redirect("checkout:checkout_info")

    context = {
        "breadcrumbs": build_breadcrumbs(("Cart", "/cart/"), ("Checkout", "")),
        "cart": get_cart_summary(request),
        "form": form,
        "allow_guest_checkout": allow_guest_checkout,
    }
    return render_storefront(
        request,
        "checkout/auth.html",
        context,
        page_title="Checkout Authentication",
        page_description="Sign in or continue as a guest before completing checkout.",
    )


def checkout_info_view(request):
    cart = get_or_create_cart(request)
    if cart.is_empty:
        return redirect("cart:cart_page")

    checkout_settings = get_checkout_settings_cached(request)
    allow_guest_checkout = bool(getattr(checkout_settings, "allow_guest_checkout", True))
    if not request.user.is_authenticated and not allow_guest_checkout and not get_checkout_state(request).get("email"):
        return redirect("checkout:checkout_auth")

    form = CheckoutContactForm(request.POST or None, initial=get_checkout_prefill(request))
    if request.method == "POST" and form.is_valid():
        update_checkout_state(request, **form.cleaned_data)
        if form.cleaned_data.get("email"):
            cart.email = form.cleaned_data["email"]
            cart.shipping_country = form.cleaned_data.get("country_code", "")
            cart.shipping_state = form.cleaned_data.get("state", "")
            cart.shipping_postal_code = form.cleaned_data.get("postal_code", "")
            cart.save(update_fields=["email", "shipping_country", "shipping_state", "shipping_postal_code", "updated_at"])
        return redirect("checkout:checkout_shipping")

    context = {
        "breadcrumbs": build_breadcrumbs(("Cart", "/cart/"), ("Checkout", "/checkout/auth/"), ("Information", "")),
        "cart": get_cart_summary(request),
        "form": form,
    }
    return render_storefront(
        request,
        "checkout/info.html",
        context,
        page_title="Checkout Information",
        page_description="Capture customer and delivery information for the active checkout.",
    )


def checkout_shipping_view(request):
    cart = get_or_create_cart(request)
    checkout_state = get_checkout_state(request)
    if not checkout_state.get("address1"):
        return redirect("checkout:checkout_info")

    methods = get_shipping_methods(request, cart)
    form = ShippingMethodForm(
        request.POST or None,
        methods=methods,
        initial={"shipping_method": checkout_state.get("shipping_method")},
    )
    if request.method == "POST" and form.is_valid():
        update_checkout_state(request, shipping_method=form.cleaned_data["shipping_method"])
        return redirect("checkout:checkout_payment")

    context = {
        "breadcrumbs": build_breadcrumbs(("Cart", "/cart/"), ("Information", "/checkout/info/"), ("Shipping", "")),
        "cart": get_cart_summary(request),
        "form": form,
        "shipping_methods": methods,
    }
    return render_storefront(
        request,
        "checkout/shipping.html",
        context,
        page_title="Shipping Method",
        page_description="Choose how the order should be delivered.",
    )


def checkout_payment_view(request):
    checkout_state = get_checkout_state(request)
    if not checkout_state.get("shipping_method"):
        return redirect("checkout:checkout_shipping")

    methods = get_payment_methods(request)
    form = PaymentMethodForm(
        request.POST or None,
        methods=methods,
        initial={"payment_method": checkout_state.get("payment_method")},
    )
    if request.method == "POST" and form.is_valid():
        update_checkout_state(request, payment_method=form.cleaned_data["payment_method"])
        return redirect("checkout:checkout_review")

    context = {
        "breadcrumbs": build_breadcrumbs(("Cart", "/cart/"), ("Shipping", "/checkout/shipping/"), ("Payment", "")),
        "cart": get_cart_summary(request),
        "form": form,
        "payment_methods": methods,
    }
    return render_storefront(
        request,
        "checkout/payment.html",
        context,
        page_title="Payment",
        page_description="Select the payment method for this order.",
    )


def checkout_review_view(request):
    checkout_state = get_checkout_state(request)
    if not checkout_state.get("payment_method"):
        return redirect("checkout:checkout_payment")

    if request.method == "POST":
        try:
            order = create_order_from_checkout(request)
            messages.success(request, "Order placed successfully.")
            return redirect("checkout:order_confirmation", order_id=order.id)
        except ValueError as exc:
            messages.error(request, str(exc))

    context = {
        "breadcrumbs": build_breadcrumbs(("Cart", "/cart/"), ("Payment", "/checkout/payment/"), ("Review", "")),
        "cart": get_cart_summary(request),
        "checkout_state": checkout_state,
    }
    return render_storefront(
        request,
        "checkout/review.html",
        context,
        page_title="Review Order",
        page_description="Review checkout details before placing the order.",
    )


def payment_callback_view(request):
    order_id = request.GET.get("order_id") or request.POST.get("order_id")
    status = request.GET.get("status") or request.POST.get("status") or "pending"
    reference = request.GET.get("reference") or request.POST.get("reference") or ""
    order = Order.objects.filter(id=order_id).first() if order_id else None
    if order is None:
        messages.error(request, "Payment callback could not resolve an order.")
        return redirect("cart:cart_page")

    update_order_payment_state(order, status=status, reference=reference)
    if status.lower() in {"success", "paid", "completed"}:
        messages.success(request, "Payment confirmed.")
    elif status.lower() in {"failed", "cancelled", "voided"}:
        messages.error(request, "Payment failed or was cancelled.")
    return redirect("checkout:order_confirmation", order_id=order.id)


def payment_webhook_view(request):
    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            payload = {}

    order_id = payload.get("order_id") or request.POST.get("order_id")
    status = payload.get("status") or request.POST.get("status") or "pending"
    reference = payload.get("reference") or request.POST.get("reference") or ""

    if not order_id:
        return JsonResponse({"ok": False, "error": "order_id is required"}, status=400)

    order = Order.objects.filter(id=order_id).first()
    if order is None:
        return JsonResponse({"ok": False, "error": "order not found"}, status=404)

    update_order_payment_state(order, status=status, reference=reference, payload=payload)
    return JsonResponse({"ok": True, "order_id": str(order.id), "status": status})


def express_checkout_view(request):
    cart = get_or_create_cart(request)
    if cart.is_empty:
        messages.error(request, "Your cart is empty.")
        return redirect("cart:cart_page")
    if request.user.is_authenticated:
        update_checkout_state(request, email=request.user.email)
    return redirect("checkout:checkout_info")


def order_confirmation_view(request, order_id):
    order = get_order_for_request(request, order_id)
    if order is None:
        messages.error(request, "That order could not be found for this session.")
        return redirect("cart:cart_page")

    context = {
        "breadcrumbs": build_breadcrumbs(("Cart", "/cart/"), ("Checkout", "/checkout/review/"), ("Confirmation", "")),
        "order": order,
        "shipping_address": order.addresses.filter(address_type=OrderAddress.AddressType.SHIPPING).first(),
    }
    clear_checkout_state(request)
    return render_storefront(
        request,
        "checkout/confirmation.html",
        context,
        page_title=f"Order {order.order_number}",
        page_description="Order confirmation and next-step details.",
    )
