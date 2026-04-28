"""dashboard/pricing/views/tax.py — TaxCategory, TaxZone, TaxRate CRUD views."""
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.sidebar_utiles import main_sidebar
from dashboard.pricing.models import TaxCategory, TaxZone, TaxRate
from dashboard.pricing.forms import TaxCategoryForm, TaxZoneForm, TaxRateForm

logger = logging.getLogger("pricing.views.tax")


def _ctx(prefix, page_title, active_menu="pricing_tax", **extra):
    base = {"prefix": prefix, "page_title": page_title,
            "active_menu": active_menu, "sidebar": main_sidebar(prefix)}
    base.update(extra)
    return base


# ─────────────────────────────────────────────────────────────
# TAX CATEGORY
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def tax_category_list(request, prefix):
    qs = TaxCategory.objects.all().order_by("sort_order", "name")
    ctx = _ctx(prefix, "Tax Categories", categories=qs,
               create_url=reverse("dashboard:pricing:tax_category_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_category/list.html", ctx)


@login_required
@dashboard_prefix_required
def tax_category_create(request, prefix):
    form = TaxCategoryForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Tax category created.")
                return redirect(reverse("dashboard:pricing:tax_category_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("tax_category_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add Tax Category", form=form, is_edit=False, form_title="Add Tax Category",
               list_url=reverse("dashboard:pricing:tax_category_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_category/form.html", ctx)


@login_required
@dashboard_prefix_required
def tax_category_edit(request, prefix, pk):
    obj = get_object_or_404(TaxCategory, pk=pk)
    form = TaxCategoryForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Tax category updated.")
                return redirect(reverse("dashboard:pricing:tax_category_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("tax_category_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit — {obj.name}", form=form, is_edit=True, object=obj,
               form_title=f"Edit Tax Category — {obj.name}",
               list_url=reverse("dashboard:pricing:tax_category_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_category/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def tax_category_delete(request, prefix, pk):
    obj = get_object_or_404(TaxCategory, pk=pk)
    try:
        if obj.is_default:
            messages.error(request, "Cannot delete the default tax category. Reassign default first.")
        else:
            obj.delete()
            messages.success(request, f"Tax category '{obj.name}' deleted.")
    except Exception as exc:
        logger.error("tax_category_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:tax_category_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# TAX ZONE
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def tax_zone_list(request, prefix):
    qs = TaxZone.objects.all().order_by("-priority", "name")
    ctx = _ctx(prefix, "Tax Zones", zones=qs,
               create_url=reverse("dashboard:pricing:tax_zone_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_zone/list.html", ctx)


@login_required
@dashboard_prefix_required
def tax_zone_create(request, prefix):
    form = TaxZoneForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Tax zone created.")
                return redirect(reverse("dashboard:pricing:tax_zone_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("tax_zone_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add Tax Zone", form=form, is_edit=False, form_title="Add Tax Zone",
               list_url=reverse("dashboard:pricing:tax_zone_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_zone/form.html", ctx)


@login_required
@dashboard_prefix_required
def tax_zone_edit(request, prefix, pk):
    obj = get_object_or_404(TaxZone, pk=pk)
    form = TaxZoneForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Tax zone updated.")
                return redirect(reverse("dashboard:pricing:tax_zone_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("tax_zone_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit — {obj.name}", form=form, is_edit=True, object=obj,
               form_title=f"Edit Tax Zone — {obj.name}",
               list_url=reverse("dashboard:pricing:tax_zone_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_zone/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def tax_zone_delete(request, prefix, pk):
    obj = get_object_or_404(TaxZone, pk=pk)
    try:
        obj.delete()
        messages.success(request, f"Tax zone '{obj.name}' deleted.")
    except Exception as exc:
        logger.error("tax_zone_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:tax_zone_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# TAX RATE
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def tax_rate_list(request, prefix):
    zone_pk = request.GET.get("zone", "")
    qs = TaxRate.objects.select_related("tax_zone", "tax_category").all()
    if zone_pk:
        qs = qs.filter(tax_zone__pk=zone_pk)
    zones = TaxZone.objects.all().order_by("name")
    ctx = _ctx(prefix, "Tax Rates", rates=qs, zones=zones, selected_zone=zone_pk,
               create_url=reverse("dashboard:pricing:tax_rate_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_rate/list.html", ctx)


@login_required
@dashboard_prefix_required
def tax_rate_create(request, prefix):
    form = TaxRateForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Tax rate created.")
                return redirect(reverse("dashboard:pricing:tax_rate_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("tax_rate_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add Tax Rate", form=form, is_edit=False, form_title="Add Tax Rate",
               list_url=reverse("dashboard:pricing:tax_rate_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_rate/form.html", ctx)


@login_required
@dashboard_prefix_required
def tax_rate_edit(request, prefix, pk):
    obj = get_object_or_404(TaxRate, pk=pk)
    form = TaxRateForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Tax rate updated.")
                return redirect(reverse("dashboard:pricing:tax_rate_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("tax_rate_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit — {obj.name}", form=form, is_edit=True, object=obj,
               form_title=f"Edit Tax Rate — {obj.name}",
               list_url=reverse("dashboard:pricing:tax_rate_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/tax_rate/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def tax_rate_delete(request, prefix, pk):
    obj = get_object_or_404(TaxRate, pk=pk)
    try:
        obj.delete()
        messages.success(request, f"Tax rate '{obj.name}' deleted.")
    except Exception as exc:
        logger.error("tax_rate_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:tax_rate_list", kwargs={"prefix": prefix}))
