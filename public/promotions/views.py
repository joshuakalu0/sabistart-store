from django.contrib import messages
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

from dashboard.pricing.models import FlashSale
from public.storefront.forms import NewsletterSignupForm
from public.storefront.services import (
    apply_coupon_to_cart,
    annotate_product_pricing,
    build_breadcrumbs,
    build_catalog_page,
    get_or_create_cart,
    get_product_queryset,
    render_info_page,
    render_storefront,
)


def coupon_landing_view(request):
    promo_code = (request.GET.get("discount") or request.GET.get("code") or "").strip()
    if promo_code:
        try:
            apply_coupon_to_cart(get_or_create_cart(request), promo_code)
            messages.success(request, f"Discount code '{promo_code.upper()}' has been applied to your cart.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("cart:cart_page")

    context = build_catalog_page(
        request,
        queryset=annotate_product_pricing(get_product_queryset()).filter(is_on_sale=True),
        page_title="Coupons & Discounts",
        page_description="Current discounted products and code-enabled promotions.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Promotions", "")),
    )
    return render_storefront(request, "catalog/listing.html", context, page_title="Promotions")


def loyalty_info_view(request):
    return render_info_page(
        request,
        title="Loyalty Program",
        body="Loyalty is presented as a tenant-themed shell for now. The page is ready to connect to a points engine later.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Loyalty", ""))},
    )


def referral_landing_view(request):
    return render_info_page(
        request,
        title="Refer a Friend",
        body="Referral messaging is live, with the persistence layer intentionally deferred until a referral program is selected.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Referrals", ""))},
    )


def gift_card_buy_view(request):
    return render_info_page(
        request,
        title="Gift Cards",
        body="Gift card purchasing is displayed as a storefront shell in this pass and can be connected to the pricing domain later.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Gift Cards", ""))},
    )


def gift_card_balance_view(request):
    return render_info_page(
        request,
        title="Gift Card Balance",
        body="Gift card balance lookup is not connected to a stored-value backend yet, but the themed page is in place.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Gift Card Balance", ""))},
    )


def newsletter_signup_view(request):
    form = NewsletterSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        messages.success(request, "Newsletter signup has been recorded for this tenant.")
        return redirect("promotions:newsletter_signup")
    return render_info_page(
        request,
        title="Newsletter Signup",
        body="Join the store newsletter for launches, campaigns, and merchandising updates.",
        form=form,
        form_action=request.path,
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Newsletter", ""))},
    )


def competition_list_view(request):
    return render_info_page(
        request,
        title="Competitions",
        body="Competition landing pages are available as themed content shells until the campaign engine is expanded.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Competitions", ""))},
    )


def campaign_landing_view(request, campaign_slug):
    campaign = FlashSale.objects.filter(slug=campaign_slug, is_publicly_visible=True).first()
    if campaign:
        context = build_catalog_page(
            request,
            queryset=annotate_product_pricing(get_product_queryset()).filter(flash_sale_items__flash_sale=campaign).distinct(),
            page_title=campaign.name,
            page_description=campaign.description or "Campaign products for the active promotion.",
            breadcrumbs=build_breadcrumbs(("Home", "/"), ("Promotions", "/promotions/"), (campaign.name, "")),
            extra_context={"campaign": campaign},
        )
        return render_storefront(request, "catalog/listing.html", context, page_title=campaign.name)

    return render_info_page(
        request,
        title=f"Campaign: {campaign_slug}",
        body="The requested campaign is not currently published for this storefront.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Promotions", "/promotions/"), (campaign_slug, ""))},
    )
