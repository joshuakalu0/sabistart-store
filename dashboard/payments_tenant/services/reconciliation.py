"""Reconciliation report generation utilities."""
import logging
from django.utils import timezone

logger = logging.getLogger("payments.reconciliation")


def generate_daily_reconciliation(payment_profile, report_date=None, gateway_provider=None, currency=None):
    from dashboard.payments_tenant.models import ReconciliationReport, Transaction, TransactionStatus, CommissionEntry
    from django.db.models import Sum, Count, Q
    target_date = report_date or (timezone.now() - timezone.timedelta(days=1)).date()
    start = timezone.datetime.combine(target_date, timezone.datetime.min.time()).replace(tzinfo=timezone.utc)
    end = start + timezone.timedelta(days=1)
    qs = Transaction.objects.filter(payment_profile=payment_profile, created_at__gte=start, created_at__lt=end, status=TransactionStatus.SUCCESS)
    if gateway_provider:
        qs = qs.filter(gateway_provider=gateway_provider)
    agg = qs.aggregate(count=Count("id"), gross=Sum("amount"), commission=Sum("platform_commission"), gateway_fee=Sum("gateway_fee"), net=Sum("tenant_net"), refunds=Sum("amount_refunded"))
    report, created = ReconciliationReport.objects.update_or_create(
        payment_profile=payment_profile, report_date=target_date,
        gateway_provider=gateway_provider or "all", currency=currency or "NGN",
        defaults={
            "platform_transaction_count": agg["count"] or 0,
            "platform_gross_amount": agg["gross"] or 0,
            "platform_commission_earned": agg["commission"] or 0,
            "platform_gateway_fees": agg["gateway_fee"] or 0,
            "platform_net_credited": agg["net"] or 0,
            "platform_refund_total": agg["refunds"] or 0,
            "status": ReconciliationReport.ReportStatus.PENDING,
            "generated_at": timezone.now(),
        },
    )
    return report


def detect_discrepancies(report):
    from dashboard.payments_tenant.models import ReconciliationReport
    amount_diff = abs(report.platform_gross_amount - report.gateway_gross_amount)
    count_diff = abs(report.platform_transaction_count - report.gateway_transaction_count)
    if amount_diff > 0 or count_diff > 0:
        report.amount_discrepancy = amount_diff
        report.count_discrepancy = count_diff
        report.status = ReconciliationReport.ReportStatus.DISCREPANCY
    else:
        report.status = ReconciliationReport.ReportStatus.MATCHED
    report.save(update_fields=["amount_discrepancy", "count_discrepancy", "status", "updated_at"])
    return report.status == ReconciliationReport.ReportStatus.MATCHED


def mark_reconciliation_resolved(report_id, actor=None, note=""):
    from dashboard.payments_tenant.models import ReconciliationReport
    try:
        report = ReconciliationReport.objects.get(id=report_id)
        report.status = ReconciliationReport.ReportStatus.RESOLVED
        report.resolution_note = note
        report.discrepancy_resolved_at = timezone.now()
        report.discrepancy_resolved_by = actor
        report.save()
        return True
    except ReconciliationReport.DoesNotExist:
        return False


def get_unreconciled_transactions(payment_profile, days=7):
    from dashboard.payments_tenant.models import Transaction, TransactionStatus
    from django.db.models import Q
    cutoff = timezone.now() - timezone.timedelta(days=days)
    return list(Transaction.objects.filter(
        payment_profile=payment_profile,
        status=TransactionStatus.SUCCESS,
        created_at__gte=cutoff,
        settled_at__isnull=True,
    ).values("id", "internal_reference", "amount", "currency", "paid_at", "gateway_provider"))
