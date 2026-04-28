from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import render

from dashboard.decorators import dashboard_prefix_required
from dashboard.payments_tenant.models import (
    CommissionEntry,
    SavedPaymentMethod,
    TenantBalance,
    TenantBalanceTransaction,
)
from dashboard.payments_tenant.view_utils import build_page_context, get_payment_profile


@login_required
@dashboard_prefix_required
def balance_list(request, prefix):
    profile = get_payment_profile(request)
    balances = TenantBalance.objects.filter(payment_profile=profile).order_by("currency")
    return render(
        request,
        "dashboard/payments_tenant/balance/list.html",
        build_page_context(
            prefix,
            "Account Balance",
            "payments_balance",
            balances=balances,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def balance_transaction_list(request, prefix):
    profile = get_payment_profile(request)
    qs = TenantBalanceTransaction.objects.filter(payment_profile=profile).order_by("-created_at")

    currency_filter = request.GET.get("currency", "").strip()
    type_filter = request.GET.get("entry_type", "").strip()
    if currency_filter:
        qs = qs.filter(currency=currency_filter.upper())
    if type_filter:
        qs = qs.filter(entry_type=type_filter)

    ledger_entries = Paginator(qs, 50).get_page(request.GET.get("page", 1))
    currencies = (
        TenantBalanceTransaction.objects.filter(payment_profile=profile)
        .values_list("currency", flat=True)
        .distinct()
        .order_by("currency")
    )
    return render(
        request,
        "dashboard/payments_tenant/balance_transaction/list.html",
        build_page_context(
            prefix,
            "Balance Ledger",
            "payments_balance",
            ledger_entries=ledger_entries,
            currency_filter=currency_filter,
            type_filter=type_filter,
            available_currencies=currencies,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def commission_entry_list(request, prefix):
    profile = get_payment_profile(request)
    qs = CommissionEntry.objects.filter(payment_profile=profile).select_related("commission_rule").order_by("-created_at")
    currency_filter = request.GET.get("currency", "").strip()
    if currency_filter:
        qs = qs.filter(currency=currency_filter.upper())

    entries = Paginator(qs, 50).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/commission_entry/list.html",
        build_page_context(
            prefix,
            "Commission Entries",
            "payments_balance",
            entries=entries,
            currency_filter=currency_filter,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def saved_payment_method_list(request, prefix):
    profile = get_payment_profile(request)
    qs = SavedPaymentMethod.objects.filter(payment_profile=profile).order_by("-created_at")

    q = request.GET.get("q", "").strip()
    type_filter = request.GET.get("method_type", "").strip()
    active_filter = request.GET.get("is_active", "").strip()
    if q:
        qs = qs.filter(
            models.Q(display_name__icontains=q)
            | models.Q(last4__icontains=q)
            | models.Q(card_brand__icontains=q)
            | models.Q(bank_name__icontains=q)
        )
    if type_filter:
        qs = qs.filter(method_type=type_filter)
    if active_filter == "1":
        qs = qs.filter(status=SavedPaymentMethod.MethodStatus.ACTIVE)
    elif active_filter == "0":
        qs = qs.exclude(status=SavedPaymentMethod.MethodStatus.ACTIVE)

    methods = Paginator(qs, 30).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/saved_payment_method/list.html",
        build_page_context(
            prefix,
            "Saved Payment Methods",
            "payments_balance",
            methods=methods,
            q=q,
            type_filter=type_filter,
            active_filter=active_filter,
            profile=profile,
        ),
    )
