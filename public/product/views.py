from django.contrib import messages
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect

from public.product.models import Product
from public.storefront.forms import GuestCheckoutForm
from public.storefront.services import (
    annotate_product_pricing,
    build_breadcrumbs,
    build_flash_sale_lookup,
    get_active_flash_sale,
    get_compare_products,
    get_product_queryset,
    get_recently_viewed_products,
    get_related_product_cards,
    get_social_platforms,
    get_wishlist_products,
    push_recently_viewed_product,
    render_info_page,
    render_storefront,
    serialize_product_detail,
    toggle_session_product,
    get_or_create_cart,
    add_variant_to_cart,
)


def _resolve_product(product_slug):
    return get_object_or_404(annotate_product_pricing(get_product_queryset()), slug=product_slug)


def _handle_product_actions(request, product):
    action = request.POST.get("action")
    if action == "add_to_cart":
        cart = get_or_create_cart(request)
        variant_id = request.POST.get("variant_id") or request.POST.get("product_id")
        variant = product.variants.filter(id=variant_id, is_active=True).first() if variant_id else None
        if variant is None:
            variant = product.variants.filter(is_active=True).order_by("-is_default", "price").first()
        if variant is None:
            messages.error(request, "This product does not currently have an available variant.")
            return redirect("product:product_detail", product_slug=product.slug)
        add_variant_to_cart(cart, variant, quantity=request.POST.get("quantity", 1))
        messages.success(request, f"{product.name} was added to your cart.")
        return redirect("cart:cart_page")

    if action == "toggle_wishlist":
        added = toggle_session_product(request, "wishlist", str(product.id))
        messages.success(request, "Saved to wishlist." if added else "Removed from wishlist.")
        return redirect("product:product_detail", product_slug=product.slug)

    if action == "toggle_compare":
        added = toggle_session_product(request, "compare", str(product.id))
        messages.success(request, "Added to compare." if added else "Removed from compare.")
        return redirect("product:product_detail", product_slug=product.slug)

    return None


def _render_product_page(request, product, *, quick_view_mode=False):
    Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)
    push_recently_viewed_product(request, str(product.id))
    flash_sale_lookup = build_flash_sale_lookup(get_active_flash_sale(request))
    detail = serialize_product_detail(product, request, flash_sale_lookup=flash_sale_lookup)
    wishlist_ids = {item["id"] for item in get_wishlist_products(request)}
    compare_ids = {item["id"] for item in get_compare_products(request)}
    context = {
        "product": detail,
        "breadcrumbs": build_breadcrumbs(
            ("Home", "/"),
            ("Shop All", "/shop/"),
            (product.name, ""),
        ),
        "related_products": get_related_product_cards(product, request, limit=4),
        "recently_viewed_products": [item for item in get_recently_viewed_products(request) if item["id"] != str(product.id)][:4],
        "share_platforms": get_social_platforms(request),
        "quick_view_mode": quick_view_mode,
        "in_wishlist": str(product.id) in wishlist_ids,
        "in_compare": str(product.id) in compare_ids,
    }
    return render_storefront(
        request,
        "catalog/product_detail.html",
        context,
        page_title=product.meta_title or product.name,
        page_description=product.meta_description or product.short_description or product.description[:160],
    )


def product_detail_view(request, product_slug):
    product = _resolve_product(product_slug)
    if request.method == "POST":
        response = _handle_product_actions(request, product)
        if response is not None:
            return response
    return _render_product_page(request, product)


def product_quick_view(request, product_slug):
    return _render_product_page(request, _resolve_product(product_slug), quick_view_mode=True)


def product_compare_view(request):
    if request.method == "POST":
        product_id = request.POST.get("product_id")
        if product_id:
            added = toggle_session_product(request, "compare", product_id)
            messages.success(request, "Added to compare." if added else "Removed from compare.")
        return redirect("product:product_compare")

    context = {
        "products": get_compare_products(request),
        "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Compare", "")),
    }
    return render_storefront(
        request,
        "catalog/compare.html",
        context,
        page_title="Compare Products",
        page_description="Review products side by side using the tenant-scoped compare list.",
    )


def bundle_detail_view(request, bundle_slug):
    return product_detail_view(request, bundle_slug)


def digital_product_view(request, digital_slug):
    return product_detail_view(request, digital_slug)


def subscription_product_view(request, sub_slug):
    return product_detail_view(request, sub_slug)


def configurable_product_view(request, conf_slug):
    return product_detail_view(request, conf_slug)


def notify_me_view(request, product_slug):
    product = _resolve_product(product_slug)
    form = GuestCheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        messages.success(request, f"We recorded a restock alert request for {product.name}.")
        return redirect("product:product_detail", product_slug=product.slug)
    return render_info_page(
        request,
        title=f"Notify Me: {product.name}",
        body="Submit your email to receive a restock alert when inventory is available again.",
        form=form,
        form_action=request.path,
        extra_context={"product": serialize_product_detail(product, request)},
    )


def pre_order_view(request, product_slug):
    product = _resolve_product(product_slug)
    form = GuestCheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        messages.success(request, f"We recorded your pre-order interest for {product.name}.")
        return redirect("product:product_detail", product_slug=product.slug)
    return render_info_page(
        request,
        title=f"Pre-Order: {product.name}",
        body="This product is being offered on a pre-order basis. Leave your email to be contacted about launch timing.",
        form=form,
        form_action=request.path,
        extra_context={"product": serialize_product_detail(product, request)},
    )
