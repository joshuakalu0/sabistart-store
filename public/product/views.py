from decimal import Decimal

from django.contrib import messages
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect

from public.product.models import Product
from public.product.review_services import get_product_review_payload
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
from pricing.models import BundleOffer, BundleOfferItem


def _resolve_product(product_slug):
    return get_object_or_404(annotate_product_pricing(get_product_queryset()), slug=product_slug)


def _get_customer_profile(request):
    if getattr(request.user, "is_authenticated", False):
        return get_or_create_cart(request).customer or None
    return None


def _serialize_bundle_offer(bundle: BundleOffer, request) -> dict:
    cart = get_or_create_cart(request)
    currency_code = cart.currency or "USD"
    item_rows = []
    for item in bundle.items.select_related("product", "variant", "category").order_by("sort_order", "created_at"):
        target_product = item.product or getattr(item.variant, "product", None)
        target_variant = item.variant or (
            target_product.variants.filter(is_active=True).order_by("-is_default", "price").first()
            if target_product is not None
            else None
        )
        if target_product is not None:
            product_card = annotate_product_pricing(Product.objects.filter(pk=target_product.pk)).first() or target_product
            detail = serialize_product_detail(product_card, request)
        else:
            detail = None
        item_rows.append(
            {
                "id": str(item.id),
                "role": item.role,
                "role_label": item.get_role_display(),
                "is_choice": item.role == BundleOfferItem.ItemRole.CHOICE,
                "is_required": item.role == BundleOfferItem.ItemRole.REQUIRED,
                "quantity": int(item.quantity or 1),
                "product": detail,
                "variant_id": str(target_variant.id) if target_variant else "",
                "category_name": getattr(item.category, "name", ""),
                "discounted_unit_price": item.discounted_unit_price,
                "discounted_unit_price_display": f"{currency_code} {Decimal(item.discounted_unit_price):,.2f}" if item.discounted_unit_price is not None else "",
                "discount_percentage": item.discount_percentage,
                "is_selectable": item.role == BundleOfferItem.ItemRole.CHOICE and bool(target_variant),
            }
        )

    link_path = f"/bundles/{bundle.slug}/"
    return {
        "id": str(bundle.id),
        "slug": bundle.slug,
        "name": bundle.name,
        "public_title": bundle.public_title or bundle.name,
        "description": bundle.description,
        "offer_type": bundle.offer_type,
        "offer_type_label": bundle.get_offer_type_display(),
        "bundle_price": bundle.bundle_price,
        "bundle_price_display": f"{currency_code} {Decimal(bundle.bundle_price or 0):,.2f}",
        "required_quantity": bundle.required_quantity,
        "min_selection": bundle.min_selection,
        "max_selection": bundle.max_selection,
        "is_mix_match": bundle.offer_type == BundleOffer.OfferType.MIX_MATCH,
        "is_fixed_bundle": bundle.offer_type == BundleOffer.OfferType.FIXED,
        "is_upsell_bundle": bundle.offer_type == BundleOffer.OfferType.UPSELL,
        "badge_label": bundle.badge_label or "Bundle Deal",
        "share_copy": bundle.share_copy or "Build this bundle and save instantly.",
        "share_url": request.build_absolute_uri(link_path),
        "items": item_rows,
    }


def _add_bundle_offer_to_cart(request, bundle: BundleOffer):
    cart = get_or_create_cart(request)
    added = 0
    items = list(bundle.items.select_related("product", "variant").order_by("sort_order", "created_at"))
    selected_choice_ids = {value for value in request.POST.getlist("choice_item") if value}
    choice_items = [item for item in items if item.role == BundleOfferItem.ItemRole.CHOICE]
    required_items = [item for item in items if item.role != BundleOfferItem.ItemRole.CHOICE]

    active_choice_items = []
    for item in choice_items:
        variant = item.variant
        if variant is None and item.product_id:
            variant = item.product.variants.filter(is_active=True).order_by("-is_default", "price").first()
        if variant is not None:
            active_choice_items.append((item, variant))

    selected_choice_items = []
    if bundle.offer_type == BundleOffer.OfferType.MIX_MATCH:
        if selected_choice_ids:
            for item, variant in active_choice_items:
                if str(item.id) in selected_choice_ids:
                    selected_choice_items.append((item, variant))
        else:
            selected_choice_items = active_choice_items[: max(1, int(bundle.min_selection or 1))]

        selected_count = len(selected_choice_items)
        min_selection = max(0, int(bundle.min_selection or 0))
        max_selection = int(bundle.max_selection or 0) if bundle.max_selection else None
        if selected_count < min_selection:
            raise ValueError(f"Choose at least {min_selection} bundle option{'s' if min_selection != 1 else ''}.")
        if max_selection and selected_count > max_selection:
            raise ValueError(f"Choose no more than {max_selection} bundle option{'s' if max_selection != 1 else ''}.")

    for item in required_items:
        variant = item.variant
        if variant is None and item.product_id:
            variant = item.product.variants.filter(is_active=True).order_by("-is_default", "price").first()
        if variant is None:
            continue
        add_variant_to_cart(cart, variant, quantity=max(1, int(item.quantity or 1)))
        added += 1

    for item, variant in selected_choice_items:
        add_variant_to_cart(cart, variant, quantity=max(1, int(item.quantity or 1)))
        added += 1
    return added


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
    customer = get_or_create_cart(request).customer if getattr(request.user, "is_authenticated", False) else None
    wishlist_ids = {item["id"] for item in get_wishlist_products(request)}
    compare_ids = {item["id"] for item in get_compare_products(request)}
    context = {
        "product": detail,
        "review_bundle": get_product_review_payload(product, customer=customer),
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
    bundle = get_object_or_404(
        BundleOffer.objects.prefetch_related("items__product__images", "items__product__variants", "items__variant", "items__category"),
        slug=bundle_slug,
        is_active=True,
        is_public=True,
    )
    if request.method == "POST" and request.POST.get("action") == "add_bundle_to_cart":
        try:
            added_count = _add_bundle_offer_to_cart(request, bundle)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("product:bundle_detail", bundle_slug=bundle.slug)
        if added_count:
            messages.success(request, f"{bundle.public_title or bundle.name} was added to your cart.")
        else:
            messages.error(request, "This bundle does not currently have purchasable items.")
        return redirect("cart:cart_page")

    context = {
        "bundle_offer": _serialize_bundle_offer(bundle, request),
        "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Bundles", "/bundles/"), (bundle.public_title or bundle.name, "")),
    }
    return render_storefront(
        request,
        "catalog/bundle_detail.html",
        context,
        page_title=bundle.public_title or bundle.name,
        page_description=bundle.description or bundle.share_copy or bundle.name,
    )


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
