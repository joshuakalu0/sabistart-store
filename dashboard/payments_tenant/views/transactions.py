import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from dashboard.decorators import dashboard_prefix_required
from dashboard.payments_tenant.models import PaymentIntent, Transaction
from dashboard.payments_tenant.services import flag_transaction, unflag_transaction
from dashboard.payments_tenant.view_utils import build_page_context, get_payment_profile

logger = logging.getLogger("dashboard.payments_tenant.views.transactions")


@login_required
@dashboard_prefix_required
def payment_intent_list(request, prefix):
    profile = get_payment_profile(request)
    qs = PaymentIntent.objects.filter(payment_profile=profile).order_by("-created_at")

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    if q:
        qs = qs.filter(
            Q(order_number__icontains=q)
            | Q(customer_email__icontains=q)
            | Q(gateway_intent_id__icontains=q)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)

    intents = Paginator(qs, 30).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/payment_intent/list.html",
        build_page_context(
            prefix,
            "Payment Intents",
            "payments_transactions",
            intents=intents,
            q=q,
            status_filter=status_filter,
            profile=profile,
            status_choices=PaymentIntent.IntentStatus.choices,
        ),
    )


@login_required
@dashboard_prefix_required
def transaction_list(request, prefix):
    profile = get_payment_profile(request)
    qs = (
        Transaction.objects.filter(payment_profile=profile)
        .select_related("gateway_mode__gateway")
        .order_by("-created_at")
    )

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    gateway_filter = request.GET.get("gateway", "").strip()
    flagged_only = request.GET.get("flagged", "") == "1"
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if q:
        qs = qs.filter(
            Q(order_number__icontains=q)
            | Q(customer_email__icontains=q)
            | Q(internal_reference__icontains=q)
            | Q(gateway_reference__icontains=q)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if gateway_filter:
        qs = qs.filter(gateway_provider=gateway_filter)
    if flagged_only:
        qs = qs.filter(is_flagged=True)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    transactions = Paginator(qs, 30).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/transaction/list.html",
        build_page_context(
            prefix,
            "Transactions",
            "payments_transactions",
            transactions=transactions,
            q=q,
            status_filter=status_filter,
            gateway_filter=gateway_filter,
            flagged_only=flagged_only,
            date_from=date_from,
            date_to=date_to,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def transaction_detail(request, prefix, pk):
    profile = get_payment_profile(request)
    txn = get_object_or_404(
        Transaction.objects.select_related("gateway_mode__gateway", "card_detail").prefetch_related(
            "events",
            "refunds",
            "fraud_assessments",
            "disputes__evidence_items",
        ),
        pk=pk,
        payment_profile=profile,
    )
    return render(
        request,
        "dashboard/payments_tenant/transaction/detail.html",
        build_page_context(
            prefix,
            f"Transaction - {txn.internal_reference}",
            "payments_transactions",
            txn=txn,
            events=txn.events.order_by("created_at"),
            refunds=txn.refunds.order_by("-created_at"),
            disputes=txn.disputes.order_by("-opened_at"),
            fraud_assessments=txn.fraud_assessments.order_by("-created_at"),
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def transaction_flag(request, prefix, pk):
    if request.method != "POST":
        return redirect("dashboard:payments_tenant:transaction_detail", prefix=prefix, pk=pk)

    profile = get_payment_profile(request)
    txn = get_object_or_404(Transaction, pk=pk, payment_profile=profile)
    action = request.POST.get("action", "").strip()

    try:
        if action == "flag":
            ok = flag_transaction(str(txn.id), reason=request.POST.get("flag_reason", ""), actor=request.user)
            if ok:
                messages.success(request, "Transaction flagged for review.")
            else:
                messages.error(request, "Could not flag transaction.")
        elif action == "unflag":
            ok = unflag_transaction(str(txn.id), actor=request.user)
            if ok:
                messages.success(request, "Transaction flag removed.")
            else:
                messages.error(request, "Could not remove transaction flag.")
        else:
            messages.error(request, "Invalid transaction action.")
    except Exception as exc:
        logger.exception("Failed to update transaction flag for %s: %s", pk, exc)
        messages.error(request, f"Error: {exc}")

    return redirect("dashboard:payments_tenant:transaction_detail", prefix=prefix, pk=pk)
