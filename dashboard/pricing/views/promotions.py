"""dashboard/pricing/views/promotions.py — BuyXGetY, VolumePricingTier, FlashSale views."""
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
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
    ctx = _ctx(prefix, "Buy X Get Y Promotions", promotions=qs, q=q, status=status,
               create_url=reverse("dashboard:pricing:bxgy_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/bxgy/list.html", ctx)


@login_required
@dashboard_prefix_required
def bxgy_detail(request, prefix, pk):
    obj = get_object_or_404(BuyXGetYPromotion, pk=pk)
    items = obj.eligible_items.select_related("product", "variant", "category").all()
    ctx = _ctx(prefix, f"BXGY — {obj.title}", promotion=obj, items=items,
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
    items = promo.eligible_items.select_related("product", "variant", "category").all()
    ctx = _ctx(prefix, f"Items — {promo.title}", promotion=promo, items=items,
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
    qs = VolumePricingTier.objects.select_related("variant", "customer_group").filter(is_active=True)
    ctx = _ctx(prefix, "Volume Pricing Tiers", active_menu="pricing_volume",
               tiers=qs,
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
    qs = FlashSale.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    if status == "live":
        qs = qs.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)
    elif status == "upcoming":
        qs = qs.filter(is_active=True, starts_at__gt=now)
    elif status == "ended":
        qs = qs.filter(ends_at__lte=now)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    now_ts = now.isoformat()
    ctx = _ctx(prefix, "Flash Sales", active_menu="pricing_flash",
               sales=qs, q=q, status=status, now_ts=now_ts,
               create_url=reverse("dashboard:pricing:flash_sale_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/flash_sale/list.html", ctx)


@login_required
@dashboard_prefix_required
def flash_sale_detail(request, prefix, pk):
    obj = get_object_or_404(FlashSale, pk=pk)
    items = obj.items.select_related("product", "variant").all()
    ctx = _ctx(prefix, f"Flash Sale — {obj.name}", active_menu="pricing_flash", sale=obj, items=items,
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
    items = sale.items.select_related("product", "variant").all()
    ctx = _ctx(prefix, f"Items — {sale.name}", active_menu="pricing_flash", sale=sale, items=items,
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
