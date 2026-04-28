import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from dashboard.decorators import dashboard_prefix_required
from dashboard.payments_tenant.forms import DisputeEvidenceForm, RefundForm
from dashboard.payments_tenant.models import Dispute, Refund, Transaction
from dashboard.payments_tenant.services import request_refund
from dashboard.payments_tenant.view_utils import build_page_context, get_payment_profile

logger = logging.getLogger("dashboard.payments_tenant.views.refunds_disputes")


@login_required
@dashboard_prefix_required
def refund_list(request, prefix):
    profile = get_payment_profile(request)
    qs = Refund.objects.filter(payment_profile=profile).select_related("transaction").order_by("-created_at")

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    if q:
        qs = qs.filter(transaction__internal_reference__icontains=q)
    if status_filter:
        qs = qs.filter(status=status_filter)

    refunds = Paginator(qs, 30).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/refund/list.html",
        build_page_context(
            prefix,
            "Refunds",
            "payments_refunds",
            refunds=refunds,
            q=q,
            status_filter=status_filter,
            status_choices=Refund.RefundStatus.choices,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def refund_detail(request, prefix, pk):
    profile = get_payment_profile(request)
    refund = get_object_or_404(
        Refund.objects.select_related("transaction").prefetch_related("line_items"),
        pk=pk,
        payment_profile=profile,
    )
    return render(
        request,
        "dashboard/payments_tenant/refund/detail.html",
        build_page_context(
            prefix,
            f"Refund - {refund.refund_reference}",
            "payments_refunds",
            refund=refund,
            line_items=refund.line_items.all(),
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def refund_create(request, prefix, transaction_pk):
    profile = get_payment_profile(request)
    txn = get_object_or_404(Transaction, pk=transaction_pk, payment_profile=profile)

    if txn.status != "success":
        messages.error(request, f"Cannot refund a transaction with status '{txn.status}'.")
        return redirect("dashboard:payments_tenant:transaction_detail", prefix=prefix, pk=transaction_pk)

    if request.method == "POST":
        form = RefundForm(request.POST, transaction=txn)
        if form.is_valid():
            try:
                refund = request_refund(
                    transaction=txn,
                    amount=form.cleaned_data["amount"],
                    reason=form.cleaned_data["reason"],
                    reason_detail=form.cleaned_data.get("reason_detail", ""),
                    customer_note=form.cleaned_data.get("customer_note", ""),
                    internal_note=form.cleaned_data.get("internal_note", ""),
                    initiated_by=request.user,
                )
                messages.success(request, f"Refund {refund.refund_reference} processed successfully.")
                return redirect("dashboard:payments_tenant:refund_detail", prefix=prefix, pk=refund.pk)
            except Exception as exc:
                logger.exception("Failed to create refund for %s: %s", transaction_pk, exc)
                messages.error(request, f"Refund failed: {exc}")
    else:
        form = RefundForm(transaction=txn)

    return render(
        request,
        "dashboard/payments_tenant/refund/detail.html",
        build_page_context(
            prefix,
            f"Initiate Refund - {txn.internal_reference}",
            "payments_refunds",
            form=form,
            txn=txn,
            is_refund_form=True,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def dispute_list(request, prefix):
    profile = get_payment_profile(request)
    qs = Dispute.objects.filter(payment_profile=profile).select_related("transaction").order_by("-opened_at")

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    overdue_only = request.GET.get("overdue", "") == "1"
    now = timezone.now()

    if q:
        qs = qs.filter(transaction__internal_reference__icontains=q)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if overdue_only:
        qs = qs.filter(status=Dispute.DisputeStatus.OPEN, evidence_deadline__lt=now)

    disputes = Paginator(qs, 30).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/dispute/list.html",
        build_page_context(
            prefix,
            "Disputes",
            "payments_disputes",
            disputes=disputes,
            q=q,
            status_filter=status_filter,
            overdue_only=overdue_only,
            now=now,
            status_choices=Dispute.DisputeStatus.choices,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def dispute_detail(request, prefix, pk):
    profile = get_payment_profile(request)
    dispute = get_object_or_404(
        Dispute.objects.select_related("transaction").prefetch_related("evidence_items"),
        pk=pk,
        payment_profile=profile,
    )
    now = timezone.now()
    evidence_deadline_passed = bool(dispute.evidence_deadline and dispute.evidence_deadline < now)

    return render(
        request,
        "dashboard/payments_tenant/dispute/detail.html",
        build_page_context(
            prefix,
            f"Dispute - {dispute.dispute_reference}",
            "payments_disputes",
            dispute=dispute,
            evidence_list=dispute.evidence_items.order_by("-created_at"),
            evidence_deadline_passed=evidence_deadline_passed,
            now=now,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def dispute_evidence_create(request, prefix, dispute_pk):
    profile = get_payment_profile(request)
    dispute = get_object_or_404(Dispute, pk=dispute_pk, payment_profile=profile)
    now = timezone.now()

    if dispute.status != Dispute.DisputeStatus.OPEN:
        messages.error(request, "Evidence can only be submitted for open disputes.")
        return redirect("dashboard:payments_tenant:dispute_detail", prefix=prefix, pk=dispute_pk)

    if dispute.evidence_deadline and dispute.evidence_deadline < now:
        messages.error(request, "The evidence submission deadline for this dispute has passed.")
        return redirect("dashboard:payments_tenant:dispute_detail", prefix=prefix, pk=dispute_pk)

    if request.method == "POST":
        form = DisputeEvidenceForm(request.POST)
        if form.is_valid():
            evidence = form.save(commit=False)
            evidence.dispute = dispute
            evidence.submitted_at = now
            evidence.submitted_by = request.user
            evidence.save()
            messages.success(request, f"Evidence '{evidence.get_evidence_type_display()}' submitted.")
            return redirect("dashboard:payments_tenant:dispute_detail", prefix=prefix, pk=dispute_pk)
    else:
        form = DisputeEvidenceForm()

    return render(
        request,
        "dashboard/payments_tenant/dispute_evidence/form.html",
        build_page_context(
            prefix,
            f"Submit Evidence - {dispute.dispute_reference}",
            "payments_disputes",
            form_title="Submit Dispute Evidence",
            form=form,
            dispute=dispute,
            profile=profile,
        ),
    )
