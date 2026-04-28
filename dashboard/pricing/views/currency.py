"""dashboard/pricing/views/currency.py — Currency & ExchangeRate CRUD views."""
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.sidebar_utiles import main_sidebar
from dashboard.pricing.models import Currency, ExchangeRate
from dashboard.pricing.forms import CurrencyForm, ExchangeRateForm

logger = logging.getLogger("pricing.views.currency")

# ── Helpers ──────────────────────────────────────────────────
def _ctx(prefix, page_title, active_menu="pricing_currency", **extra):
    base = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix),
    }
    base.update(extra)
    return base


# ─────────────────────────────────────────────────────────────
# CURRENCY
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def currency_list(request, prefix):
    q = request.GET.get("q", "").strip()
    qs = Currency.objects.all()
    if q:
        qs = qs.filter(code__icontains=q) | Currency.objects.filter(name__icontains=q)
        qs = qs.distinct()
    ctx = _ctx(prefix, "Currencies", currencies=qs, q=q,
               create_url=reverse("dashboard:pricing:currency_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/currency/list.html", ctx)


@login_required
@dashboard_prefix_required
def currency_create(request, prefix):
    form = CurrencyForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Currency created successfully.")
                return redirect(reverse("dashboard:pricing:currency_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("currency_create error: %s", exc)
                messages.error(request, f"Error creating currency: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add Currency", form=form, is_edit=False,
               form_title="Add Currency",
               list_url=reverse("dashboard:pricing:currency_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/currency/form.html", ctx)


@login_required
@dashboard_prefix_required
def currency_edit(request, prefix, pk):
    obj = get_object_or_404(Currency, pk=pk)
    form = CurrencyForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Currency updated.")
                return redirect(reverse("dashboard:pricing:currency_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("currency_edit error: %s", exc)
                messages.error(request, f"Error updating currency: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit {obj}", form=form, is_edit=True, object=obj,
               form_title=f"Edit Currency — {obj.code}",
               list_url=reverse("dashboard:pricing:currency_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/currency/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def currency_delete(request, prefix, pk):
    obj = get_object_or_404(Currency, pk=pk)
    try:
        if obj.is_base_currency:
            messages.error(request, "Cannot delete the base currency. Reassign base currency first.")
        else:
            obj.delete()
            messages.success(request, f"Currency '{obj.code}' deleted.")
    except Exception as exc:
        logger.error("currency_delete error: %s", exc)
        messages.error(request, f"Error deleting currency: {exc}")
    return redirect(reverse("dashboard:pricing:currency_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# EXCHANGE RATE
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def exchange_rate_list(request, prefix):
    qs = ExchangeRate.objects.select_related("base_currency", "target_currency").all()
    ctx = _ctx(prefix, "Exchange Rates", active_menu="pricing_exchange",
               rates=qs,
               create_url=reverse("dashboard:pricing:exchange_rate_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/exchange_rate/list.html", ctx)


@login_required
@dashboard_prefix_required
def exchange_rate_create(request, prefix):
    form = ExchangeRateForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Exchange rate created.")
                return redirect(reverse("dashboard:pricing:exchange_rate_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("exchange_rate_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add Exchange Rate", active_menu="pricing_exchange",
               form=form, is_edit=False, form_title="Add Exchange Rate",
               list_url=reverse("dashboard:pricing:exchange_rate_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/exchange_rate/form.html", ctx)


@login_required
@dashboard_prefix_required
def exchange_rate_edit(request, prefix, pk):
    obj = get_object_or_404(ExchangeRate, pk=pk)
    form = ExchangeRateForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Exchange rate updated.")
                return redirect(reverse("dashboard:pricing:exchange_rate_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("exchange_rate_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Rate — {obj}", active_menu="pricing_exchange",
               form=form, is_edit=True, object=obj, form_title=str(obj),
               list_url=reverse("dashboard:pricing:exchange_rate_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/exchange_rate/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def exchange_rate_delete(request, prefix, pk):
    obj = get_object_or_404(ExchangeRate, pk=pk)
    try:
        obj.delete()
        messages.success(request, "Exchange rate deleted.")
    except Exception as exc:
        logger.error("exchange_rate_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:exchange_rate_list", kwargs={"prefix": prefix}))
