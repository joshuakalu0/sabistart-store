"""
Combined analytics + dashboard utilities.
Re-exports analytics functions and dashboard functions.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

logger = logging.getLogger("payments.analytics")


def get_revenue_over_time(payment_profile, start, end, granularity="day", currency=None):
    from dashboard.payments_tenant.models import CommissionEntry
    trunc_fn = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}.get(granularity, TruncDate)
    qs = CommissionEntry.objects.filter(payment_profile=payment_profile, created_at__gte=start, created_at__lte=end)
    if currency: qs = qs.filter(currency=currency)
    rows = qs.annotate(period=trunc_fn("created_at")).values("period").annotate(gross=Sum("gross_amount"), commission=Sum("platform_commission"), gateway_fee=Sum("gateway_fee"), net=Sum("tenant_net"), count=Count("id")).order_by("period")
    return [{"period": r["period"].strftime("%Y-%m-%d"), "gross": float(r["gross"] or 0), "commission": float(r["commission"] or 0), "net": float(r["net"] or 0), "transaction_count": r["count"]} for r in rows]


def get_transaction_funnel(payment_profile, start, end):
    from dashboard.payments_tenant.models import PaymentIntent, Transaction, TransactionStatus
    total = PaymentIntent.objects.filter(payment_profile=payment_profile, created_at__gte=start, created_at__lte=end).count()
    succeeded = Transaction.objects.filter(payment_profile=payment_profile, status=TransactionStatus.SUCCESS, created_at__gte=start, created_at__lte=end).count()
    failed = Transaction.objects.filter(payment_profile=payment_profile, status=TransactionStatus.FAILED, created_at__gte=start, created_at__lte=end).count()
    abandoned = PaymentIntent.objects.filter(payment_profile=payment_profile, status__in=["abandoned","expired"], created_at__gte=start, created_at__lte=end).count()
    p = lambda n, d: round(n/d*100, 1) if d > 0 else 0.0
    return [
        {"stage": "Checkout Initiated", "count": total,     "pct": 100.0},
        {"stage": "Payment Succeeded",  "count": succeeded, "pct": p(succeeded, total)},
        {"stage": "Payment Failed",     "count": failed,    "pct": p(failed, total)},
        {"stage": "Abandoned/Expired",  "count": abandoned, "pct": p(abandoned, total)},
    ]


def get_gateway_performance(payment_profile, start, end):
    from dashboard.payments_tenant.models import Transaction, TransactionStatus
    rows = Transaction.objects.filter(payment_profile=payment_profile, created_at__gte=start, created_at__lte=end).values("gateway_provider").annotate(total=Count("id"), succeeded=Count("id", filter=Q(status=TransactionStatus.SUCCESS)), failed=Count("id", filter=Q(status=TransactionStatus.FAILED)), gross_volume=Sum("amount", filter=Q(status=TransactionStatus.SUCCESS)), net_volume=Sum("tenant_net", filter=Q(status=TransactionStatus.SUCCESS))).order_by("-gross_volume")
    return [{"gateway_provider": r["gateway_provider"], "total_attempts": r["total"], "succeeded": r["succeeded"], "failed": r["failed"], "success_rate": round(r["succeeded"]/r["total"]*100,1) if r["total"] else 0.0, "gross_volume": float(r["gross_volume"] or 0), "net_volume": float(r["net_volume"] or 0)} for r in rows]


def get_payment_method_breakdown(payment_profile, start, end):
    from dashboard.payments_tenant.models import Transaction, TransactionStatus
    rows = Transaction.objects.filter(payment_profile=payment_profile, status=TransactionStatus.SUCCESS, created_at__gte=start, created_at__lte=end).values("payment_method_type").annotate(count=Count("id"), volume=Sum("amount")).order_by("-volume")
    total = sum(float(r["volume"] or 0) for r in rows)
    return [{"payment_method": r["payment_method_type"] or "unknown", "count": r["count"], "volume": float(r["volume"] or 0), "pct": round(float(r["volume"] or 0)/total*100,1) if total else 0.0} for r in rows]


def get_refund_analysis(payment_profile, start, end):
    from dashboard.payments_tenant.models import Refund, Transaction, TransactionStatus
    ragg = Refund.objects.filter(payment_profile=payment_profile, created_at__gte=start, created_at__lte=end).aggregate(count=Count("id"), total=Sum("amount"), commission_reversed=Sum("commission_reversed"))
    gross = Transaction.objects.filter(payment_profile=payment_profile, status=TransactionStatus.SUCCESS, created_at__gte=start, created_at__lte=end).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    rtotal = ragg["total"] or Decimal("0")
    by_reason = list(Refund.objects.filter(payment_profile=payment_profile, created_at__gte=start, created_at__lte=end).values("reason").annotate(count=Count("id"), total=Sum("amount")).order_by("-count"))
    return {"total_refunds": ragg["count"] or 0, "total_refunded": float(rtotal), "refund_rate_pct": round(float(rtotal/gross*100),2) if gross else 0.0, "commission_reversed": float(ragg["commission_reversed"] or 0), "by_reason": [{"reason": r["reason"], "count": r["count"], "amount": float(r["total"] or 0)} for r in by_reason]}


def get_dispute_analysis(payment_profile, start, end):
    from dashboard.payments_tenant.models import Dispute
    agg = Dispute.objects.filter(payment_profile=payment_profile, opened_at__gte=start, opened_at__lte=end).aggregate(total=Count("id"), amount=Sum("dispute_amount"), won=Count("id", filter=Q(status="won")), lost=Count("id", filter=Q(status="lost")), open=Count("id", filter=Q(status="open")))
    total = agg["total"] or 0; won = agg["won"] or 0
    return {"total_disputes": total, "total_amount": float(agg["amount"] or 0), "won": won, "lost": agg["lost"] or 0, "open": agg["open"] or 0, "win_rate_pct": round(won/total*100,1) if total else 0.0}


def get_commission_earned_over_time(start, end, granularity="day"):
    from dashboard.payments_tenant.models import CommissionEntry
    trunc_fn = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}.get(granularity, TruncDate)
    rows = CommissionEntry.objects.filter(created_at__gte=start, created_at__lte=end).annotate(period=trunc_fn("created_at")).values("period").annotate(commission=Sum("platform_commission"), volume=Sum("gross_amount"), count=Count("id")).order_by("period")
    return [{"period": r["period"].strftime("%Y-%m-%d"), "commission_earned": float(r["commission"] or 0), "gross_volume": float(r["volume"] or 0), "count": r["count"]} for r in rows]


def get_payout_history_chart(payment_profile, start, end):
    from dashboard.payments_tenant.models import PayoutRequest
    rows = PayoutRequest.objects.filter(payment_profile=payment_profile, status="completed", completed_at__gte=start, completed_at__lte=end).annotate(period=TruncDate("completed_at")).values("period","currency").annotate(total=Sum("amount"), count=Count("id")).order_by("period")
    return [{"period": r["period"].strftime("%Y-%m-%d"), "currency": r["currency"], "total_paid_out": float(r["total"] or 0), "count": r["count"]} for r in rows]


def get_failed_payment_analysis(payment_profile, start, end):
    from dashboard.payments_tenant.models import Transaction, TransactionStatus
    failed = Transaction.objects.filter(payment_profile=payment_profile, status=TransactionStatus.FAILED, created_at__gte=start, created_at__lte=end)
    by_gw = list(failed.values("gateway_provider").annotate(count=Count("id"), amount=Sum("amount")).order_by("-count"))
    top_reasons = list(failed.exclude(gateway_message="").values("gateway_message").annotate(count=Count("id")).order_by("-count")[:10])
    return {"total_failed": failed.count(), "by_gateway": [{"gateway": r["gateway_provider"], "count": r["count"], "amount": float(r["amount"] or 0)} for r in by_gw], "top_reasons": [{"reason": r["gateway_message"][:80], "count": r["count"]} for r in top_reasons]}


def get_top_customers_by_spend(payment_profile, start, end, limit=10):
    from dashboard.payments_tenant.models import Transaction, TransactionStatus
    rows = Transaction.objects.filter(payment_profile=payment_profile, status=TransactionStatus.SUCCESS, created_at__gte=start, created_at__lte=end).exclude(customer_email="").values("customer_email","customer_id").annotate(total_spend=Sum("amount"), count=Count("id"), avg=Avg("amount")).order_by("-total_spend")[:limit]
    return [{"customer_email": r["customer_email"], "customer_id": str(r["customer_id"]) if r["customer_id"] else None, "total_spend": float(r["total_spend"] or 0), "count": r["count"], "avg_order_value": float(r["avg"] or 0)} for r in rows]


# ── Dashboard functions ──

def get_payments_dashboard_kpis(payment_profile, period_days=30):
    from dashboard.payments_tenant.models import Transaction, CommissionEntry, Refund, TransactionStatus, TenantBalance, PayoutRequest
    now = timezone.now(); ps = now - timedelta(days=period_days); prev = ps - timedelta(days=period_days)
    def _stats(s, e):
        ta = Transaction.objects.filter(payment_profile=payment_profile, created_at__gte=s, created_at__lte=e).aggregate(total=Count("id"), succeeded=Count("id", filter=Q(status=TransactionStatus.SUCCESS)), failed=Count("id", filter=Q(status=TransactionStatus.FAILED)), gross=Sum("amount", filter=Q(status=TransactionStatus.SUCCESS)), avg=Avg("amount", filter=Q(status=TransactionStatus.SUCCESS)))
        ca = CommissionEntry.objects.filter(payment_profile=payment_profile, created_at__gte=s, created_at__lte=e).aggregate(commission=Sum("platform_commission"), net=Sum("tenant_net"))
        return {"total": ta["total"] or 0, "succeeded": ta["succeeded"] or 0, "failed": ta["failed"] or 0, "gross": float(ta["gross"] or 0), "avg": float(ta["avg"] or 0), "commission": float(ca["commission"] or 0), "net": float(ca["net"] or 0)}
    curr = _stats(ps, now); prev_d = _stats(prev, ps)
    chg = lambda c, p: round((c-p)/p*100, 1) if p and p != 0 else 0.0
    sr = round(curr["succeeded"]/curr["total"]*100, 1) if curr["total"] else 0.0
    balances = list(TenantBalance.objects.filter(payment_profile=payment_profile).values("currency","available_balance","pending_balance"))
    pp = PayoutRequest.objects.filter(payment_profile=payment_profile, status__in=["pending","approved"]).aggregate(count=Count("id"), total=Sum("amount"))
    return {
        "period_days": period_days,
        "gross_revenue":   {"value": curr["gross"],     "change_pct": chg(curr["gross"],     prev_d["gross"]),     "format": "currency"},
        "net_revenue":     {"value": curr["net"],       "change_pct": chg(curr["net"],       prev_d["net"]),       "format": "currency"},
        "commission_paid": {"value": curr["commission"],"change_pct": chg(curr["commission"],prev_d["commission"]),"format": "currency"},
        "transactions":    {"value": curr["succeeded"], "change_pct": chg(curr["succeeded"], prev_d["succeeded"]), "format": "integer"},
        "failed_payments": {"value": curr["failed"],    "change_pct": chg(curr["failed"],    prev_d["failed"]),    "format": "integer"},
        "success_rate":    {"value": sr, "format": "percentage"},
        "avg_order_value": {"value": curr["avg"],       "change_pct": chg(curr["avg"],       prev_d["avg"]),       "format": "currency"},
        "balances": balances,
        "pending_payouts": {"count": pp["count"] or 0, "total": float(pp["total"] or 0)},
    }


def get_gateway_status_overview(payment_profile):
    from dashboard.payments_tenant.models import TenantGatewayMode
    modes = TenantGatewayMode.objects.filter(payment_profile=payment_profile).select_related("gateway","direct_credential","platform_credential")
    return [{"id": str(gm.id), "gateway_provider": gm.gateway.provider, "gateway_name": gm.gateway.name, "mode": gm.mode, "mode_label": "Direct Mode" if gm.is_direct_mode else "Platform Mode", "status": gm.status, "is_active": gm.is_active, "is_default": gm.is_default, "has_own_credentials": gm.direct_credential is not None, "credential_status": gm.direct_credential.status if gm.direct_credential else None, "subaccount_code": gm.platform_subaccount_code if gm.is_platform_mode else "", "split_percentage": float(gm.split_percentage) if gm.split_percentage else None, "total_transactions": gm.total_transactions, "total_volume": float(gm.total_volume), "can_switch_to_direct": gm.gateway.is_available_for_direct_mode} for gm in modes.order_by("-is_default","gateway__display_order")]


def get_recent_transactions(payment_profile, limit=20):
    from dashboard.payments_tenant.models import Transaction
    txns = Transaction.objects.filter(payment_profile=payment_profile).select_related("gateway_mode__gateway").order_by("-created_at")[:limit]
    return [{"id": str(t.id), "internal_reference": t.internal_reference, "order_number": t.order_number, "status": t.status, "amount": float(t.amount), "currency": t.currency, "customer_email": t.customer_email, "gateway_provider": t.gateway_provider, "payment_mode": t.payment_mode, "is_flagged": t.is_flagged, "paid_at": t.paid_at.isoformat() if t.paid_at else None, "created_at": t.created_at.isoformat()} for t in txns]


def get_payments_health_checks(payment_profile):
    from dashboard.payments_tenant.models import TenantGatewayMode, TenantBankAccount, Dispute
    checks = []
    active_gw = TenantGatewayMode.objects.filter(payment_profile=payment_profile, status="active").count()
    checks.append({"check": "active_gateway", "status": "ok" if active_gw else "error", "message": f"{active_gw} active gateway(s)." if active_gw else "No active gateway — customers cannot pay."})
    has_default = TenantGatewayMode.objects.filter(payment_profile=payment_profile, is_default=True, status="active").exists()
    checks.append({"check": "default_gateway", "status": "ok" if has_default else "warning", "message": "Default gateway set." if has_default else "No default gateway."})
    checks.append({"check": "payout_enabled", "status": "ok" if payment_profile.payout_enabled else "warning", "message": "Payout enabled." if payment_profile.payout_enabled else "Payout not enabled."})
    kyb_ok = payment_profile.kyb_status == "verified"
    checks.append({"check": "kyb_status", "status": "ok" if kyb_ok else "warning", "message": "KYB verified." if kyb_ok else f"KYB status: {payment_profile.kyb_status}"})
    banks = TenantBankAccount.objects.filter(payment_profile=payment_profile, status="verified").count()
    checks.append({"check": "bank_account", "status": "ok" if banks else "warning", "message": f"{banks} verified bank account(s)." if banks else "No verified bank account."})
    checks.append({"check": "account_status", "status": "ok" if payment_profile.is_operational else "error", "message": f"Account {payment_profile.account_status}."})
    open_disp = Dispute.objects.filter(payment_profile=payment_profile, status="open").count()
    checks.append({"check": "open_disputes", "status": "warning" if open_disp else "ok", "message": f"{open_disp} open dispute(s)." if open_disp else "No open disputes."})
    return checks


def get_payout_queue_summary(payment_profile=None):
    from dashboard.payments_tenant.models import PayoutRequest
    qs = PayoutRequest.objects
    if payment_profile: qs = qs.filter(payment_profile=payment_profile)
    def _agg(s): a = qs.filter(status=s).aggregate(c=Count("id"), t=Sum("amount")); return {"count": a["c"] or 0, "total": float(a["t"] or 0)}
    p = _agg("pending"); ap = _agg("approved"); pr = _agg("processing")
    return {"pending": p, "approved": ap, "processing": pr, "total_queued": p["count"]+ap["count"]+pr["count"]}


def get_fraud_alert_summary(payment_profile=None):
    from dashboard.payments_tenant.models import Transaction, FraudAssessment
    now = timezone.now(); h24 = now - timedelta(hours=24)
    qs = Transaction.objects
    if payment_profile: qs = qs.filter(payment_profile=payment_profile)
    fq = FraudAssessment.objects
    if payment_profile: fq = fq.filter(payment_profile=payment_profile)
    return {"flagged_last_24h": qs.filter(is_flagged=True, created_at__gte=h24).count(), "total_flagged": qs.filter(is_flagged=True).count(), "high_risk_24h": fq.filter(risk_score__gte=50, created_at__gte=h24).count(), "blocked_24h": fq.filter(decision="block", created_at__gte=h24).count()}


def get_balance_overview(payment_profile):
    from dashboard.payments_tenant.models import TenantBalance, PayoutRequest
    balances = list(TenantBalance.objects.filter(payment_profile=payment_profile))
    cp = PayoutRequest.objects.filter(payment_profile=payment_profile, status="completed").aggregate(total=Sum("amount"), count=Count("id"))
    return {"balances": [{"currency": b.currency, "available": float(b.available_balance), "pending": float(b.pending_balance), "reserved": float(b.reserved_balance), "total": float(b.total_balance), "can_payout": b.available_balance >= payment_profile.minimum_payout_amount, "minimum_payout": float(payment_profile.minimum_payout_amount)} for b in balances], "total_paid_out_all_time": float(cp["total"] or 0), "payout_count": cp["count"] or 0, "payout_enabled": payment_profile.payout_enabled}


def get_payments_attention_queue(payment_profile=None):
    from dashboard.payments_tenant.models import Transaction, Dispute, PayoutRequest, TenantGatewayMode
    now = timezone.now()
    base = {"payment_profile": payment_profile} if payment_profile else {}
    flagged = Transaction.objects.filter(is_flagged=True, **base).count()
    overdue = Dispute.objects.filter(status="open", evidence_deadline__lt=now, **base).count()
    open_d = Dispute.objects.filter(status="open", evidence_deadline__gte=now, **base).count()
    pending = PayoutRequest.objects.filter(status="pending", **base).count()
    inactive = TenantGatewayMode.objects.filter(payment_profile=payment_profile, status="inactive").count() if payment_profile else 0
    return {"total_issues": flagged+overdue+open_d+pending, "flagged_transactions": flagged, "overdue_disputes": overdue, "open_disputes": open_d, "pending_payout_reviews": pending, "inactive_gateways": inactive, "requires_urgent_attention": overdue > 0 or flagged > 5}
