from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from dashboard.decorators import dashboard_prefix_required
from dashboard.payments_tenant.models import ReconciliationReport
from dashboard.payments_tenant.view_utils import build_page_context, get_payment_profile


@login_required
@dashboard_prefix_required
def tenant_reconciliation_list(request, prefix):
    profile = get_payment_profile(request)
    qs = ReconciliationReport.objects.filter(payment_profile=profile).order_by("-report_date")
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    reports = Paginator(qs, 25).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/reconciliation/list.html",
        build_page_context(
            prefix,
            "Reconciliation Reports",
            "payments_analytics",
            reports=reports,
            status_filter=status_filter,
            status_choices=ReconciliationReport.ReportStatus.choices,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def tenant_reconciliation_detail(request, prefix, pk):
    profile = get_payment_profile(request)
    report = get_object_or_404(
        ReconciliationReport.objects.prefetch_related("entries"),
        pk=pk,
        payment_profile=profile,
    )

    entries_qs = report.entries.all().order_by("-created_at")
    match_filter = request.GET.get("match_status", "").strip()
    if match_filter == "matched":
        entries_qs = entries_qs.filter(entry_status="matched")
    elif match_filter == "mismatch":
        entries_qs = entries_qs.exclude(entry_status="matched")
    elif match_filter == "missing_in_gateway":
        entries_qs = entries_qs.filter(entry_status="platform_only")
    elif match_filter == "missing_in_platform":
        entries_qs = entries_qs.filter(entry_status="gateway_only")

    entries = Paginator(entries_qs, 50).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/reconciliation/detail.html",
        build_page_context(
            prefix,
            f"Reconciliation - {report.report_date}",
            "payments_analytics",
            report=report,
            entries=entries,
            match_filter=match_filter,
            match_status_choices=[
                ("matched", "Matched"),
                ("mismatch", "Mismatch"),
                ("missing_in_gateway", "Missing in Gateway"),
                ("missing_in_platform", "Missing in Platform"),
            ],
            profile=profile,
        ),
    )
