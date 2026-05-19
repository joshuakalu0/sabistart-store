"""dashboard/pricing/views/promotions.py — BuyXGetY, VolumePricingTier, FlashSale views."""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from dashboard.decorators import dashboard_prefix_required
from dashboard.sidebar_utiles import main_sidebar
from dashboard.pricing.models import (
    BuyXGetYPromotion, BuyXGetYItem,
    VolumePricingTier,
    FlashSale, FlashSaleItem,
)
from dashboard.pricing.forms import (
    BuyXGetYPromotionForm, BuyXGetYItemForm,
    VolumePricingTierForm,
    FlashSaleForm, FlashSaleItemForm,
)

logger = logging.getLogger("pricing.views.promotions")


def _ctx(prefix, page_title, active_menu="pricing_promotions", **extra):
    base = {"prefix": prefix, "page_title": page_title,
            "active_menu": active_menu, "sidebar": main_sidebar(prefix)}
    base.update(extra)
    return base


def _paginate(request, items, per_page=20):
    paginator = Paginator(items, per_page)
    return paginator.get_page(request.GET.get("page"))


def _decorate_bxgy(promotion):
    promotion.bxgy = promotion
    promotion.name = promotion.title
    promotion.discount_percent = promotion.get_discount_percentage
    promotion.item_count = promotion.items.count()
    return promotion


def _decorate_bxgy_item(item):
    item.is_buy_item = item.side == item.Side.BUY
    item.is_get_item = item.side == item.Side.GET
    item.display_product = item.product or getattr(item.variant, "product", None)
    if item.display_product and item.product is None:
        item.product = item.display_product
    item.display_variant = item.variant
    item.bxgy = item.promotion
    return item


def _decorate_volume_tier(tier):
    tier.product = tier.variant.product
    tier.name = f"{tier.variant.product.name} • {tier.variant.variant_name or tier.variant.sku or 'Volume Tier'}"
    tier.quantity = tier.min_quantity
    if tier.price_type == "percentage":
        tier.discount_type = "percentage"
        tier.discount_value = tier.discount_percentage
    elif tier.price_type == "fixed_discount":
        tier.discount_type = "fixed_discount"
        tier.discount_value = tier.fixed_discount
    else:
        tier.discount_type = "fixed"
        tier.discount_value = tier.price
    return tier


def _decorate_flash_sale(sale):
    now = timezone.now()
    sale.item_count = sale.items.count()
    if sale.ends_at and sale.ends_at <= now:
        sale.dashboard_status = "ended"
    elif sale.starts_at and sale.starts_at > now:
        sale.dashboard_status = "upcoming"
    elif sale.is_active:
        sale.dashboard_status = "live"
    else:
        sale.dashboard_status = "inactive"
    return sale


def _decorate_flash_sale_item(item):
    item.display_product = item.product or getattr(item.variant, "product", None)
    if item.display_product and item.product is None:
        item.product = item.display_product
    item.quantity_limit = item.stock_limit
    if item.sale_price is not None:
        item.flash_price = item.sale_price
    elif item.discount_percentage is not None:
        item.flash_price = f"{item.discount_percentage:.0f}% off"
    else:
        item.flash_price = "Uses sale default"
    return item


# ─────────────────────────────────────────────────────────────
# BUY X GET Y PROMOTION
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def bxgy_list(request, prefix):
    q = request.GET.get("q", "").strip()
    qs = BuyXGetYPromotion.objects.all()
    if q:
        qs = qs.filter(title__icontains=q)
    status = request.GET.get("status", "")
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    campaigns = [_decorate_bxgy(obj) for obj in qs.order_by("-starts_at", "-created_at")]
    page_obj = _paginate(request, campaigns, per_page=20)
    ctx = _ctx(prefix, "Buy X Get Y Promotions", promotions=page_obj, campaigns=page_obj, q=q, status=status,
               create_url=reverse("dashboard:pricing:bxgy_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/bxgy/list.html", ctx)


@login_required
@dashboard_prefix_required
def bxgy_detail(request, prefix, pk):
    obj = get_object_or_404(BuyXGetYPromotion, pk=pk)
    items = [_decorate_bxgy_item(item) for item in obj.items.select_related("product", "variant__product", "category").all()]
    promotion = _decorate_bxgy(obj)
    ctx = _ctx(prefix, f"BXGY — {obj.title}", promotion=promotion, bxgy=promotion, items=items,
               edit_url=reverse("dashboard:pricing:bxgy_edit", kwargs={"prefix": prefix, "pk": pk}),
               items_url=reverse("dashboard:pricing:bxgy_item_list", kwargs={"prefix": prefix, "promotion_pk": pk}))
    return render(request, "dashboard/pricing/bxgy/detail.html", ctx)


@login_required
@dashboard_prefix_required
def bxgy_create(request, prefix):
    form = BuyXGetYPromotionForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Buy X Get Y promotion created.")
                return redirect(reverse("dashboard:pricing:bxgy_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("bxgy_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add BXGY Promotion", form=form, is_edit=False, form_title="Add Buy X Get Y",
               list_url=reverse("dashboard:pricing:bxgy_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/bxgy/form.html", ctx)


@login_required
@dashboard_prefix_required
def bxgy_edit(request, prefix, pk):
    obj = get_object_or_404(BuyXGetYPromotion, pk=pk)
    form = BuyXGetYPromotionForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Promotion updated.")
                return redirect(reverse("dashboard:pricing:bxgy_detail", kwargs={"prefix": prefix, "pk": pk}))
            except Exception as exc:
                logger.error("bxgy_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit — {obj.title}", form=form, is_edit=True, object=obj,
               form_title=f"Edit — {obj.title}",
               list_url=reverse("dashboard:pricing:bxgy_list", kwargs={"prefix": prefix}),
               detail_url=reverse("dashboard:pricing:bxgy_detail", kwargs={"prefix": prefix, "pk": pk}))
    return render(request, "dashboard/pricing/bxgy/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def bxgy_delete(request, prefix, pk):
    obj = get_object_or_404(BuyXGetYPromotion, pk=pk)
    try:
        obj.delete()
        messages.success(request, f"Promotion '{obj.title}' deleted.")
    except Exception as exc:
        logger.error("bxgy_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:bxgy_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# BUY X GET Y ITEM (child of BuyXGetYPromotion)
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def bxgy_item_list(request, prefix, promotion_pk):
    promo = get_object_or_404(BuyXGetYPromotion, pk=promotion_pk)
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    qs = promo.items.select_related("product", "variant__product", "category").all()
    if q:
        qs = qs.filter(
            Q(product__name__icontains=q)
            | Q(variant__variant_name__icontains=q)
            | Q(variant__sku__icontains=q)
            | Q(category__name__icontains=q)
        )
    if role in {BuyXGetYItem.Side.BUY, BuyXGetYItem.Side.GET}:
        qs = qs.filter(side=role)
    items = [_decorate_bxgy_item(item) for item in qs.order_by("side", "created_at")]
    page_obj = _paginate(request, items, per_page=20)
    promotion = _decorate_bxgy(promo)
    ctx = _ctx(prefix, f"Items — {promo.title}", promotion=promotion, bxgy=promotion, items=page_obj, q=q, role=role,
               create_url=reverse("dashboard:pricing:bxgy_item_create", kwargs={"prefix": prefix, "promotion_pk": promotion_pk}),
               detail_url=reverse("dashboard:pricing:bxgy_detail", kwargs={"prefix": prefix, "pk": promotion_pk}))
    return render(request, "dashboard/pricing/bxgy_item/list.html", ctx)


@login_required
@dashboard_prefix_required
def bxgy_item_create(request, prefix, promotion_pk):
    promo = get_object_or_404(BuyXGetYPromotion, pk=promotion_pk)
    form = BuyXGetYItemForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    item = form.save(commit=False)
                    item.promotion = promo
                    item.save()
                messages.success(request, "Item added.")
                return redirect(reverse("dashboard:pricing:bxgy_item_list", kwargs={"prefix": prefix, "promotion_pk": promotion_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Add Item — {promo.title}", form=form, is_edit=False, promotion=promo, form_title="Add Eligible Item",
               list_url=reverse("dashboard:pricing:bxgy_item_list", kwargs={"prefix": prefix, "promotion_pk": promotion_pk}))
    return render(request, "dashboard/pricing/bxgy_item/form.html", ctx)


@login_required
@dashboard_prefix_required
def bxgy_item_edit(request, prefix, promotion_pk, pk):
    promo = get_object_or_404(BuyXGetYPromotion, pk=promotion_pk)
    obj = get_object_or_404(BuyXGetYItem, pk=pk, promotion=promo)
    form = BuyXGetYItemForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Item updated.")
                return redirect(reverse("dashboard:pricing:bxgy_item_list", kwargs={"prefix": prefix, "promotion_pk": promotion_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Item — {promo.title}", form=form, is_edit=True, promotion=promo, object=obj, form_title="Edit Item",
               list_url=reverse("dashboard:pricing:bxgy_item_list", kwargs={"prefix": prefix, "promotion_pk": promotion_pk}))
    return render(request, "dashboard/pricing/bxgy_item/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def bxgy_item_delete(request, prefix, promotion_pk, pk):
    promo = get_object_or_404(BuyXGetYPromotion, pk=promotion_pk)
    obj = get_object_or_404(BuyXGetYItem, pk=pk, promotion=promo)
    try:
        obj.delete()
        messages.success(request, "Item removed.")
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:bxgy_item_list", kwargs={"prefix": prefix, "promotion_pk": promotion_pk}))


# ─────────────────────────────────────────────────────────────
# VOLUME PRICING TIER
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def volume_tier_list(request, prefix):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = VolumePricingTier.objects.select_related("variant__product", "customer_group").all()
    if q:
        qs = qs.filter(
            Q(variant__product__name__icontains=q)
            | Q(variant__variant_name__icontains=q)
            | Q(variant__sku__icontains=q)
            | Q(customer_group__name__icontains=q)
        )
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    tiers = [_decorate_volume_tier(tier) for tier in qs.order_by("variant__product__name", "min_quantity", "created_at")]
    page_obj = _paginate(request, tiers, per_page=20)
    ctx = _ctx(prefix, "Volume Pricing Tiers", active_menu="pricing_volume",
               tiers=page_obj, q=q, status=status,
               create_url=reverse("dashboard:pricing:volume_tier_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/volume_tier/list.html", ctx)


@login_required
@dashboard_prefix_required
def volume_tier_create(request, prefix):
    form = VolumePricingTierForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Volume tier created.")
                return redirect(reverse("dashboard:pricing:volume_tier_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("volume_tier_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add Volume Tier", active_menu="pricing_volume", form=form, is_edit=False, form_title="Add Volume Tier",
               list_url=reverse("dashboard:pricing:volume_tier_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/volume_tier/form.html", ctx)


@login_required
@dashboard_prefix_required
def volume_tier_edit(request, prefix, pk):
    obj = get_object_or_404(VolumePricingTier, pk=pk)
    form = VolumePricingTierForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Volume tier updated.")
                return redirect(reverse("dashboard:pricing:volume_tier_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("volume_tier_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Volume Tier", active_menu="pricing_volume", form=form, is_edit=True, object=obj, form_title="Edit Volume Tier",
               list_url=reverse("dashboard:pricing:volume_tier_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/volume_tier/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def volume_tier_delete(request, prefix, pk):
    obj = get_object_or_404(VolumePricingTier, pk=pk)
    try:
        obj.delete()
        messages.success(request, "Volume tier deleted.")
    except Exception as exc:
        logger.error("volume_tier_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:volume_tier_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# FLASH SALE
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def flash_sale_list(request, prefix):
    now = timezone.now()
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = FlashSale.objects.prefetch_related("items").all()
    if q:
        qs = qs.filter(name__icontains=q)
    if status in {"active", "live"}:
        qs = qs.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)
    elif status == "upcoming":
        qs = qs.filter(is_active=True, starts_at__gt=now)
    elif status == "ended":
        qs = qs.filter(ends_at__lte=now)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    now_ts = now.isoformat()
    sales = [_decorate_flash_sale(sale) for sale in qs.order_by("-starts_at", "-created_at")]
    page_obj = _paginate(request, sales, per_page=20)
    ctx = _ctx(prefix, "Flash Sales", active_menu="pricing_flash",
               sales=page_obj, q=q, status=status, now_ts=now_ts,
               create_url=reverse("dashboard:pricing:flash_sale_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/flash_sale/list.html", ctx)


@login_required
@dashboard_prefix_required
def flash_sale_detail(request, prefix, pk):
    obj = get_object_or_404(FlashSale, pk=pk)
    items = [_decorate_flash_sale_item(item) for item in obj.items.select_related("product", "variant__product").all()]
    sale = _decorate_flash_sale(obj)
    ctx = _ctx(prefix, f"Flash Sale — {obj.name}", active_menu="pricing_flash", sale=sale, items=items,
               now_ts=timezone.now().isoformat(),
               edit_url=reverse("dashboard:pricing:flash_sale_edit", kwargs={"prefix": prefix, "pk": pk}),
               items_url=reverse("dashboard:pricing:flash_sale_item_list", kwargs={"prefix": prefix, "sale_pk": pk}))
    return render(request, "dashboard/pricing/flash_sale/detail.html", ctx)


@login_required
@dashboard_prefix_required
def flash_sale_create(request, prefix):
    form = FlashSaleForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    sale = form.save(commit=False)
                    sale.created_by = request.user
                    sale.save()
                messages.success(request, "Flash sale created.")
                return redirect(reverse("dashboard:pricing:flash_sale_detail", kwargs={"prefix": prefix, "pk": sale.pk}))
            except Exception as exc:
                logger.error("flash_sale_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Create Flash Sale", active_menu="pricing_flash", form=form, is_edit=False, form_title="Create Flash Sale",
               list_url=reverse("dashboard:pricing:flash_sale_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/flash_sale/form.html", ctx)


@login_required
@dashboard_prefix_required
def flash_sale_edit(request, prefix, pk):
    obj = get_object_or_404(FlashSale, pk=pk)
    form = FlashSaleForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Flash sale updated.")
                return redirect(reverse("dashboard:pricing:flash_sale_detail", kwargs={"prefix": prefix, "pk": pk}))
            except Exception as exc:
                logger.error("flash_sale_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit — {obj.name}", active_menu="pricing_flash", form=form, is_edit=True, object=obj,
               form_title=f"Edit Flash Sale — {obj.name}",
               list_url=reverse("dashboard:pricing:flash_sale_list", kwargs={"prefix": prefix}),
               detail_url=reverse("dashboard:pricing:flash_sale_detail", kwargs={"prefix": prefix, "pk": pk}))
    return render(request, "dashboard/pricing/flash_sale/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def flash_sale_delete(request, prefix, pk):
    obj = get_object_or_404(FlashSale, pk=pk)
    try:
        obj.delete()
        messages.success(request, f"Flash sale '{obj.name}' deleted.")
    except Exception as exc:
        logger.error("flash_sale_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:flash_sale_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# FLASH SALE ITEM (child of FlashSale)
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def flash_sale_item_list(request, prefix, sale_pk):
    sale = get_object_or_404(FlashSale, pk=sale_pk)
    q = request.GET.get("q", "").strip()
    qs = sale.items.select_related("product", "variant__product").all()
    if q:
        qs = qs.filter(
            Q(product__name__icontains=q)
            | Q(variant__variant_name__icontains=q)
            | Q(variant__sku__icontains=q)
        )
    items = [_decorate_flash_sale_item(item) for item in qs.order_by("created_at")]
    page_obj = _paginate(request, items, per_page=20)
    sale = _decorate_flash_sale(sale)
    ctx = _ctx(prefix, f"Items — {sale.name}", active_menu="pricing_flash", sale=sale, items=page_obj, q=q,
               create_url=reverse("dashboard:pricing:flash_sale_item_create", kwargs={"prefix": prefix, "sale_pk": sale_pk}),
               detail_url=reverse("dashboard:pricing:flash_sale_detail", kwargs={"prefix": prefix, "pk": sale_pk}))
    return render(request, "dashboard/pricing/flash_sale_item/list.html", ctx)


@login_required
@dashboard_prefix_required
def flash_sale_item_create(request, prefix, sale_pk):
    sale = get_object_or_404(FlashSale, pk=sale_pk)
    form = FlashSaleItemForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    item = form.save(commit=False)
                    item.flash_sale = sale
                    item.save()
                messages.success(request, "Item added to sale.")
                return redirect(reverse("dashboard:pricing:flash_sale_item_list", kwargs={"prefix": prefix, "sale_pk": sale_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Add Item — {sale.name}", active_menu="pricing_flash", form=form, is_edit=False, sale=sale, form_title="Add Sale Item",
               list_url=reverse("dashboard:pricing:flash_sale_item_list", kwargs={"prefix": prefix, "sale_pk": sale_pk}))
    return render(request, "dashboard/pricing/flash_sale_item/form.html", ctx)


@login_required
@dashboard_prefix_required
def flash_sale_item_edit(request, prefix, sale_pk, pk):
    sale = get_object_or_404(FlashSale, pk=sale_pk)
    obj = get_object_or_404(FlashSaleItem, pk=pk, flash_sale=sale)
    form = FlashSaleItemForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Item updated.")
                return redirect(reverse("dashboard:pricing:flash_sale_item_list", kwargs={"prefix": prefix, "sale_pk": sale_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Item — {sale.name}", active_menu="pricing_flash", form=form, is_edit=True, sale=sale, object=obj, form_title="Edit Sale Item",
               list_url=reverse("dashboard:pricing:flash_sale_item_list", kwargs={"prefix": prefix, "sale_pk": sale_pk}))
    return render(request, "dashboard/pricing/flash_sale_item/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def flash_sale_item_delete(request, prefix, sale_pk, pk):
    sale = get_object_or_404(FlashSale, pk=sale_pk)
    obj = get_object_or_404(FlashSaleItem, pk=pk, flash_sale=sale)
    try:
        obj.delete()
        messages.success(request, "Item removed from sale.")
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:flash_sale_item_list", kwargs={"prefix": prefix, "sale_pk": sale_pk}))
