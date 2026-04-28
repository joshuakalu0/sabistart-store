import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from dashboard.decorators import dashboard_prefix_required
from dashboard.payments_tenant.forms import PayoutRequestForm, TenantBankAccountForm
from dashboard.payments_tenant.models import PayoutRequest, TenantBalance, TenantBankAccount
from dashboard.payments_tenant.services import cancel_payout_request, request_payout
from dashboard.payments_tenant.view_utils import build_page_context, get_payment_profile

logger = logging.getLogger("dashboard.payments_tenant.views.payouts")


@login_required
@dashboard_prefix_required
def bank_account_list(request, prefix):
    profile = get_payment_profile(request)
    accounts = TenantBankAccount.objects.filter(payment_profile=profile).order_by("-is_primary", "-created_at")
    return render(
        request,
        "dashboard/payments_tenant/bank_account/list.html",
        build_page_context(
            prefix,
            "Bank Accounts",
            "payments_balance",
            accounts=accounts,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def bank_account_create(request, prefix):
    profile = get_payment_profile(request)
    if request.method == "POST":
        form = TenantBankAccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.payment_profile = profile
            account.added_by = request.user
            account.status = TenantBankAccount.AccountStatus.PENDING
            account.save()
            messages.success(request, "Bank account submitted for verification.")
            return redirect("dashboard:payments_tenant:bank_account_list", prefix=prefix)
    else:
        form = TenantBankAccountForm()

    return render(
        request,
        "dashboard/payments_tenant/bank_account/form.html",
        build_page_context(
            prefix,
            "Add Bank Account",
            "payments_balance",
            form_title="Add Bank Account",
            form=form,
            is_edit=False,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def bank_account_delete(request, prefix, pk):
    if request.method != "POST":
        return redirect("dashboard:payments_tenant:bank_account_list", prefix=prefix)

    profile = get_payment_profile(request)
    account = get_object_or_404(TenantBankAccount, pk=pk, payment_profile=profile)
    pending_payouts = PayoutRequest.objects.filter(
        payment_profile=profile,
        bank_account=account,
        status__in=[PayoutRequest.RequestStatus.PENDING, PayoutRequest.RequestStatus.PROCESSING],
    ).exists()
    if account.is_primary:
        messages.error(request, "Set another account as primary before removing this one.")
    elif pending_payouts:
        messages.error(request, "This account has payout requests still in progress.")
    else:
        account.delete()
        messages.success(request, "Bank account removed.")
    return redirect("dashboard:payments_tenant:bank_account_list", prefix=prefix)


@login_required
@dashboard_prefix_required
def payout_request_list(request, prefix):
    profile = get_payment_profile(request)
    qs = PayoutRequest.objects.filter(payment_profile=profile).select_related("bank_account").order_by("-requested_at")
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    payout_requests = Paginator(qs, 30).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/payout_request/list.html",
        build_page_context(
            prefix,
            "Payout Requests",
            "payments_balance",
            payout_requests=payout_requests,
            status_filter=status_filter,
            status_choices=PayoutRequest.RequestStatus.choices,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def payout_request_create(request, prefix):
    profile = get_payment_profile(request)
    balance = TenantBalance.objects.filter(payment_profile=profile, currency=profile.payout_currency).first()

    if request.method == "POST":
        form = PayoutRequestForm(request.POST, payment_profile=profile)
        if form.is_valid():
            try:
                payout = request_payout(
                    payment_profile=profile,
                    bank_account=form.cleaned_data["bank_account"],
                    amount=form.cleaned_data["amount"],
                    narration=form.cleaned_data.get("narration", ""),
                    tenant_note=form.cleaned_data.get("tenant_note", ""),
                    requested_by=request.user,
                )
                messages.success(request, f"Payout request {payout.payout_reference} submitted.")
                return redirect("dashboard:payments_tenant:payout_request_detail", prefix=prefix, pk=payout.pk)
            except Exception as exc:
                logger.exception("Failed to create payout request: %s", exc)
                messages.error(request, str(exc))
    else:
        form = PayoutRequestForm(payment_profile=profile)

    return render(
        request,
        "dashboard/payments_tenant/payout_request/form.html",
        build_page_context(
            prefix,
            "Request Payout",
            "payments_balance",
            form_title="Request a Payout",
            form=form,
            balance=balance,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def payout_request_detail(request, prefix, pk):
    profile = get_payment_profile(request)
    payout = get_object_or_404(
        PayoutRequest.objects.select_related("bank_account").prefetch_related("transfers"),
        pk=pk,
        payment_profile=profile,
    )
    return render(
        request,
        "dashboard/payments_tenant/payout_request/detail.html",
        build_page_context(
            prefix,
            f"Payout - {payout.payout_reference}",
            "payments_balance",
            payout=payout,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def payout_request_cancel(request, prefix, pk):
    if request.method != "POST":
        return redirect("dashboard:payments_tenant:payout_request_detail", prefix=prefix, pk=pk)

    profile = get_payment_profile(request)
    payout = get_object_or_404(PayoutRequest, pk=pk, payment_profile=profile)
    try:
        cancel_payout_request(payout=payout, cancelled_by=request.user)
        messages.success(request, f"Payout {payout.payout_reference} cancelled.")
    except Exception as exc:
        logger.exception("Failed to cancel payout %s: %s", pk, exc)
        messages.error(request, str(exc))
    return redirect("dashboard:payments_tenant:payout_request_list", prefix=prefix)
