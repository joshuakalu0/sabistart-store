from django.contrib import messages
from django.shortcuts import redirect

from public.cart.models import Cart
from public.storefront.services import (
    build_breadcrumbs,
    get_cart_summary,
    get_cart_session_identifier,
    get_or_create_cart,
    render_storefront,
    update_cart_from_payload,
    apply_coupon_to_cart,
)


def cart_page_view(request):
    cart = get_or_create_cart(request)
    if request.method == "POST":
        update_cart_from_payload(request, cart)
        messages.success(request, "Cart updated.")
        return redirect("cart:cart_page")

    context = {
        "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Cart", "")),
        "cart": get_cart_summary(request),
    }
    return render_storefront(
        request,
        "cart/cart.html",
        context,
        page_title="Your Shopping Cart",
        page_description="Review the tenant-scoped cart, update quantities, and continue to checkout.",
    )


def cart_update_view(request):
    cart = get_or_create_cart(request)
    if request.method == "POST":
        update_cart_from_payload(request, cart)
        messages.success(request, "Cart updated.")
    return redirect("cart:cart_page")


def apply_coupon_view(request):
    if request.method == "POST":
        cart = get_or_create_cart(request)
        try:
            apply_coupon_to_cart(cart, request.POST.get("coupon_code", ""))
            messages.success(request, "Discount code applied.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("cart:cart_page")


def cart_recover_view(request, token):
    session_identifier = get_cart_session_identifier(request)
    recovered_cart = (
        Cart.objects.filter(id=token).first()
        or Cart.objects.filter(checkout_token=str(token)).first()
    )
    if recovered_cart is None:
        messages.error(request, "That recovery link is no longer valid.")
        return redirect("cart:cart_page")

    recovered_cart.session_key = session_identifier
    recovered_cart.status = Cart.CartStatus.ACTIVE
    recovered_cart.save(update_fields=["session_key", "status", "updated_at"])
    messages.success(request, "Cart recovered.")
    return redirect("cart:cart_page")
