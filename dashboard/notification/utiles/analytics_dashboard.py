"""
notifications/utils/analytics.py + dashboard.py
================================================
Time-series analytics, funnel analysis, deliverability health,
and dashboard KPI cards for the notifications domain.
"""

import logging
import math
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import (
    Avg, Count, DecimalField, ExpressionWrapper, F, Q, Sum, Max, Min,
)
from django.db.models.functions import TruncDate, TruncHour, TruncMonth, TruncWeek
from django.utils import timezone

logger = logging.getLogger("notifications.analytics")

TWO = Decimal("0.01")
FOUR = Decimal("0.0001")


# ══════════════════════════════════════════════════════════════
# MODULE: analytics.py
# ══════════════════════════════════════════════════════════════

def get_delivery_stats(
    start: datetime,
    end: datetime,
    channel_type: str = None,
) -> dict:
    """
    Overall delivery statistics for a time window.

    Returns:
        dict: {sent, delivered, opened, clicked, bounced, failed, suppressed,
               delivery_rate, open_rate, click_rate, bounce_rate}
    """
    from notifications.models import NotificationLog, DeliveryStatus

    qs = NotificationLog.objects.filter(
        created_at__gte=start, created_at__lte=end
    )
    if channel_type:
        qs = qs.filter(channel_type=channel_type)

    agg = qs.aggregate(
        total=Count("id"),
        sent=Count("id", filter=~Q(status=DeliveryStatus.SUPPRESSED)),
        delivered=Count("id", filter=Q(status__in=[
            DeliveryStatus.DELIVERED, DeliveryStatus.OPENED, DeliveryStatus.CLICKED
        ])),
        opened=Count("id", filter=Q(status__in=[
            DeliveryStatus.OPENED, DeliveryStatus.CLICKED
        ])),
        clicked=Count("id", filter=Q(status=DeliveryStatus.CLICKED)),
        bounced=Count("id", filter=Q(status=DeliveryStatus.BOUNCED)),
        soft_bounced=Count("id", filter=Q(status=DeliveryStatus.SOFT_BOUNCED)),
        failed=Count("id", filter=Q(status=DeliveryStatus.FAILED)),
        suppressed=Count("id", filter=Q(status=DeliveryStatus.SUPPRESSED)),
        spam=Count("id", filter=Q(status=DeliveryStatus.SPAM)),
        unsubscribed=Count("id", filter=Q(status=DeliveryStatus.UNSUBSCRIBED)),
    )

    def rate(n, d):
        return round(n / d * 100, 2) if d and d > 0 else 0.0

    sent = agg["sent"] or 0
    delivered = agg["delivered"] or 0
    opened = agg["opened"] or 0
    clicked = agg["clicked"] or 0
    bounced = agg["bounced"] or 0
    spam = agg["spam"] or 0

    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "channel_type": channel_type or "all",
        "total": agg["total"] or 0,
        "sent": sent,
        "delivered": delivered,
        "opened": opened,
        "clicked": clicked,
        "bounced": bounced,
        "soft_bounced": agg["soft_bounced"] or 0,
        "failed": agg["failed"] or 0,
        "suppressed": agg["suppressed"] or 0,
        "spam": spam,
        "unsubscribed": agg["unsubscribed"] or 0,
        "delivery_rate": rate(delivered, sent),
        "open_rate": rate(opened, delivered),
        "click_rate": rate(clicked, sent),
        "click_to_open_rate": rate(clicked, opened),
        "bounce_rate": rate(bounced, sent),
        "spam_rate": rate(spam, sent),
    }


def get_channel_performance(
    start: datetime,
    end: datetime,
) -> list:
    """
    Performance breakdown by channel type.

    Returns:
        list[dict]: Per-channel metrics sorted by volume.
    """
    from notifications.models import NotificationLog, DeliveryStatus

    rows = (
        NotificationLog.objects
        .filter(created_at__gte=start, created_at__lte=end)
        .values("channel_type")
        .annotate(
            total=Count("id"),
            sent=Count("id", filter=~Q(status=DeliveryStatus.SUPPRESSED)),
            delivered=Count("id", filter=Q(status__in=[
                DeliveryStatus.DELIVERED, DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            opened=Count("id", filter=Q(status__in=[
                DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            clicked=Count("id", filter=Q(status=DeliveryStatus.CLICKED)),
            bounced=Count("id", filter=Q(status=DeliveryStatus.BOUNCED)),
            failed=Count("id", filter=Q(status=DeliveryStatus.FAILED)),
            avg_duration=Avg("duration_ms"),
        )
        .order_by("-sent")
    )

    result = []
    for row in rows:
        sent = row["sent"] or 0
        delivered = row["delivered"] or 0
        opened = row["opened"] or 0
        clicked = row["clicked"] or 0
        bounced = row["bounced"] or 0

        result.append({
            "channel_type": row["channel_type"],
            "total": row["total"] or 0,
            "sent": sent,
            "delivered": delivered,
            "opened": opened,
            "clicked": clicked,
            "bounced": bounced,
            "failed": row["failed"] or 0,
            "delivery_rate": round(delivered / sent * 100, 2) if sent > 0 else 0.0,
            "open_rate": round(opened / delivered * 100, 2) if delivered > 0 else 0.0,
            "click_rate": round(clicked / sent * 100, 2) if sent > 0 else 0.0,
            "bounce_rate": round(bounced / sent * 100, 2) if sent > 0 else 0.0,
            "avg_send_duration_ms": round(row["avg_duration"] or 0, 0),
        })

    return result


def get_template_performance(
    start: datetime,
    end: datetime,
    channel_type: str = None,
    limit: int = 20,
) -> list:
    """
    Performance metrics per notification template, ranked by volume.
    """
    from notifications.models import NotificationLog, DeliveryStatus

    qs = NotificationLog.objects.filter(created_at__gte=start, created_at__lte=end)
    if channel_type:
        qs = qs.filter(channel_type=channel_type)

    rows = (
        qs
        .exclude(template__isnull=True)
        .values("template__id", "template__name", "event_slug", "channel_type")
        .annotate(
            sent=Count("id", filter=~Q(status=DeliveryStatus.SUPPRESSED)),
            delivered=Count("id", filter=Q(status__in=[
                DeliveryStatus.DELIVERED, DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            opened=Count("id", filter=Q(status__in=[
                DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            clicked=Count("id", filter=Q(status=DeliveryStatus.CLICKED)),
            bounced=Count("id", filter=Q(status=DeliveryStatus.BOUNCED)),
            suppressed=Count("id", filter=Q(status=DeliveryStatus.SUPPRESSED)),
        )
        .order_by("-sent")[:limit]
    )

    result = []
    for row in rows:
        sent = row["sent"] or 0
        delivered = row["delivered"] or 0
        opened = row["opened"] or 0
        clicked = row["clicked"] or 0

        result.append({
            "template_id": str(row["template__id"]),
            "template_name": row["template__name"],
            "event_slug": row["event_slug"],
            "channel_type": row["channel_type"],
            "sent": sent,
            "delivered": delivered,
            "opened": opened,
            "clicked": clicked,
            "bounced": row["bounced"] or 0,
            "suppressed": row["suppressed"] or 0,
            "delivery_rate": round(delivered / sent * 100, 2) if sent > 0 else 0.0,
            "open_rate": round(opened / delivered * 100, 2) if delivered > 0 else 0.0,
            "click_rate": round(clicked / delivered * 100, 2) if delivered > 0 else 0.0,
        })

    return result


def get_delivery_funnel(start: datetime, end: datetime, channel_type: str = "email") -> list:
    """
    Delivery funnel showing drop-off at each stage.

    Returns:
        list[dict]: [{stage, count, pct_of_queued, drop_off_pct}]
    """
    from notifications.models import NotificationJob, NotificationLog, DeliveryStatus

    total_jobs = NotificationJob.objects.filter(
        created_at__gte=start, created_at__lte=end, channel_type=channel_type
    ).count()

    sent = NotificationLog.objects.filter(
        created_at__gte=start, created_at__lte=end, channel_type=channel_type,
    ).exclude(status=DeliveryStatus.SUPPRESSED).count()

    delivered = NotificationLog.objects.filter(
        created_at__gte=start, created_at__lte=end, channel_type=channel_type,
        status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.OPENED, DeliveryStatus.CLICKED],
    ).count()

    opened = NotificationLog.objects.filter(
        created_at__gte=start, created_at__lte=end, channel_type=channel_type,
        status__in=[DeliveryStatus.OPENED, DeliveryStatus.CLICKED],
    ).count()

    clicked = NotificationLog.objects.filter(
        created_at__gte=start, created_at__lte=end, channel_type=channel_type,
        status=DeliveryStatus.CLICKED,
    ).count()

    def pct(n, d):
        return round(n / d * 100, 1) if d > 0 else 0.0

    stages = [
        {"stage": "Jobs Queued", "count": total_jobs, "pct_of_queued": 100.0, "drop_off_pct": 0.0},
        {"stage": "Sent to Provider", "count": sent, "pct_of_queued": pct(sent, total_jobs), "drop_off_pct": pct(total_jobs - sent, total_jobs)},
        {"stage": "Delivered", "count": delivered, "pct_of_queued": pct(delivered, total_jobs), "drop_off_pct": pct(sent - delivered, total_jobs)},
        {"stage": "Opened", "count": opened, "pct_of_queued": pct(opened, total_jobs), "drop_off_pct": pct(delivered - opened, total_jobs)},
        {"stage": "Clicked", "count": clicked, "pct_of_queued": pct(clicked, total_jobs), "drop_off_pct": pct(opened - clicked, total_jobs)},
    ]
    return stages


def get_deliverability_health(start: datetime, end: datetime) -> dict:
    """
    Email deliverability health assessment.
    Industry thresholds:
      Bounce rate: <2% = good, 2-5% = warning, >5% = critical
      Spam rate:   <0.08% = good, 0.08-0.3% = warning, >0.3% = critical
    """
    from notifications.models import BounceRecord, SpamComplaint, NotificationLog, DeliveryStatus

    sent = NotificationLog.objects.filter(
        created_at__gte=start, created_at__lte=end, channel_type="email"
    ).exclude(status=DeliveryStatus.SUPPRESSED).count()

    hard_bounces = BounceRecord.objects.filter(
        created_at__gte=start, created_at__lte=end,
        bounce_type=BounceRecord.BounceType.HARD
    ).count()

    soft_bounces = BounceRecord.objects.filter(
        created_at__gte=start, created_at__lte=end,
        bounce_type=BounceRecord.BounceType.SOFT
    ).count()

    spam_complaints = SpamComplaint.objects.filter(
        created_at__gte=start, created_at__lte=end
    ).count()

    def rate(n, d):
        return round(n / d * 100, 4) if d > 0 else 0.0

    hard_bounce_rate = rate(hard_bounces, sent)
    spam_rate = rate(spam_complaints, sent)

    if hard_bounce_rate > 5 or spam_rate > 0.3:
        health_status = "critical"
    elif hard_bounce_rate > 2 or spam_rate > 0.08:
        health_status = "warning"
    else:
        health_status = "good"

    return {
        "sent": sent,
        "hard_bounces": hard_bounces,
        "soft_bounces": soft_bounces,
        "spam_complaints": spam_complaints,
        "hard_bounce_rate": hard_bounce_rate,
        "soft_bounce_rate": rate(soft_bounces, sent),
        "spam_rate": spam_rate,
        "health_status": health_status,
        "recommendations": _get_deliverability_recommendations(hard_bounce_rate, spam_rate),
    }


def get_engagement_over_time(
    start: datetime,
    end: datetime,
    channel_type: str = "email",
    granularity: str = "day",
) -> list:
    """
    Sent/opened/clicked time series for the engagement chart.
    """
    from notifications.models import NotificationLog, DeliveryStatus

    trunc_map = {"hour": TruncHour, "day": TruncDate, "week": TruncWeek, "month": TruncMonth}
    trunc_fn = trunc_map.get(granularity, TruncDate)

    rows = (
        NotificationLog.objects
        .filter(
            created_at__gte=start, created_at__lte=end, channel_type=channel_type
        )
        .annotate(period=trunc_fn("created_at"))
        .values("period")
        .annotate(
            sent=Count("id", filter=~Q(status=DeliveryStatus.SUPPRESSED)),
            delivered=Count("id", filter=Q(status__in=[
                DeliveryStatus.DELIVERED, DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            opened=Count("id", filter=Q(status__in=[
                DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            clicked=Count("id", filter=Q(status=DeliveryStatus.CLICKED)),
        )
        .order_by("period")
    )

    return [
        {
            "period": row["period"].strftime("%Y-%m-%d"),
            "sent": row["sent"] or 0,
            "delivered": row["delivered"] or 0,
            "opened": row["opened"] or 0,
            "clicked": row["clicked"] or 0,
        }
        for row in rows
    ]


def get_top_events_by_volume(start: datetime, end: datetime, limit: int = 10) -> list:
    """Top notification events by send volume."""
    from notifications.models import NotificationLog, DeliveryStatus

    rows = (
        NotificationLog.objects
        .filter(created_at__gte=start, created_at__lte=end)
        .values("event_slug", "channel_type")
        .annotate(
            count=Count("id"),
            open_count=Count("id", filter=Q(status__in=[
                DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
        )
        .order_by("-count")[:limit]
    )

    return [
        {
            "event_slug": row["event_slug"],
            "channel_type": row["channel_type"],
            "count": row["count"],
            "open_rate": round(row["open_count"] / row["count"] * 100, 1) if row["count"] else 0.0,
        }
        for row in rows
    ]


def get_bounce_analysis(start: datetime, end: datetime) -> dict:
    """Detailed bounce analysis by type and diagnostic patterns."""
    from notifications.models import BounceRecord

    by_type = list(
        BounceRecord.objects.filter(created_at__gte=start, created_at__lte=end)
        .values("bounce_type")
        .annotate(count=Count("id"), auto_blacklisted=Count("id", filter=Q(auto_blacklisted=True)))
        .order_by("-count")
    )

    top_diagnostics = list(
        BounceRecord.objects.filter(
            created_at__gte=start, created_at__lte=end,
            diagnostic_code__gt=""
        )
        .values("diagnostic_code")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    return {
        "by_type": by_type,
        "top_diagnostic_codes": top_diagnostics,
        "total": sum(t["count"] for t in by_type),
        "auto_blacklisted": sum(t.get("auto_blacklisted", 0) for t in by_type),
    }


def get_spam_rate_trend(start: datetime, end: datetime) -> list:
    """Daily spam rate trend for deliverability monitoring."""
    from notifications.models import SpamComplaint, NotificationLog

    rows = (
        SpamComplaint.objects
        .filter(created_at__gte=start, created_at__lte=end)
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(complaints=Count("id"))
        .order_by("date")
    )

    return [
        {
            "date": row["date"].strftime("%Y-%m-%d"),
            "complaints": row["complaints"],
        }
        for row in rows
    ]


def get_webhook_performance(start: datetime, end: datetime) -> dict:
    """Webhook delivery performance metrics."""
    from notifications.models import WebhookDeliveryAttempt

    agg = WebhookDeliveryAttempt.objects.filter(
        created_at__gte=start, created_at__lte=end
    ).aggregate(
        total=Count("id"),
        successful=Count("id", filter=Q(is_successful=True)),
        avg_response_ms=Avg("response_time_ms"),
        p95_response_ms=None,
    )

    by_endpoint = list(
        WebhookDeliveryAttempt.objects
        .filter(created_at__gte=start, created_at__lte=end)
        .values("endpoint__name", "endpoint__url")
        .annotate(
            total=Count("id"),
            successful=Count("id", filter=Q(is_successful=True)),
            avg_ms=Avg("response_time_ms"),
        )
        .order_by("-total")[:10]
    )

    total = agg["total"] or 0
    successful = agg["successful"] or 0

    return {
        "total_attempts": total,
        "successful": successful,
        "failed": total - successful,
        "success_rate": round(successful / total * 100, 2) if total > 0 else 100.0,
        "avg_response_ms": round(agg["avg_response_ms"] or 0, 0),
        "by_endpoint": [
            {
                "name": row["endpoint__name"],
                "url": (row["endpoint__url"] or "")[:60],
                "total": row["total"],
                "successful": row["successful"],
                "success_rate": round(row["successful"] / row["total"] * 100, 1) if row["total"] else 0.0,
                "avg_ms": round(row["avg_ms"] or 0, 0),
            }
            for row in by_endpoint
        ],
    }


def get_unsubscribe_trend(start: datetime, end: datetime) -> list:
    """Daily unsubscribe trend."""
    from notifications.models import NotificationPreference

    rows = (
        NotificationPreference.objects
        .filter(opted_out_at__gte=start, opted_out_at__lte=end)
        .annotate(date=TruncDate("opted_out_at"))
        .values("date", "channel_type")
        .annotate(count=Count("id"))
        .order_by("date")
    )

    return [
        {
            "date": row["date"].strftime("%Y-%m-%d"),
            "channel_type": row["channel_type"],
            "unsubscribes": row["count"],
        }
        for row in rows
    ]


def get_ab_test_results(template_id: str, start: datetime, end: datetime) -> dict:
    """A/B test performance comparison for a template and its variant."""
    from notifications.models import NotificationLog, NotificationTemplate, DeliveryStatus

    try:
        template = NotificationTemplate.objects.get(id=template_id)
    except NotificationTemplate.DoesNotExist:
        return {"error": "Template not found."}

    def get_variant_stats(variant: str) -> dict:
        qs = NotificationLog.objects.filter(
            template=template,
            ab_variant=variant,
            created_at__gte=start,
            created_at__lte=end,
        )
        agg = qs.aggregate(
            sent=Count("id", filter=~Q(status=DeliveryStatus.SUPPRESSED)),
            opened=Count("id", filter=Q(status__in=[
                DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            clicked=Count("id", filter=Q(status=DeliveryStatus.CLICKED)),
        )
        sent = agg["sent"] or 0
        opened = agg["opened"] or 0
        clicked = agg["clicked"] or 0
        return {
            "variant": variant,
            "sent": sent,
            "opened": opened,
            "clicked": clicked,
            "open_rate": round(opened / sent * 100, 2) if sent else 0.0,
            "click_rate": round(clicked / sent * 100, 2) if sent else 0.0,
        }

    a_stats = get_variant_stats("A")
    b_stats = get_variant_stats("B")

    winner = None
    if a_stats["sent"] > 0 and b_stats["sent"] > 0:
        if a_stats["open_rate"] > b_stats["open_rate"]:
            winner = "A"
        elif b_stats["open_rate"] > a_stats["open_rate"]:
            winner = "B"

    return {
        "template_id": template_id,
        "template_name": template.name,
        "ab_test_enabled": template.ab_test_enabled,
        "variant_a": a_stats,
        "variant_b": b_stats,
        "winner": winner,
        "winner_metric": "open_rate",
    }


def build_daily_summary(date=None) -> int:
    """
    Aggregate NotificationLog records into NotificationDailySummary.
    Called by a nightly Celery task.

    Returns:
        int: Number of summary records built/updated.
    """
    from notifications.models import (
        NotificationLog, NotificationDailySummary, DeliveryStatus
    )

    target_date = date or (timezone.now() - timedelta(days=1)).date()
    start = timezone.datetime.combine(target_date, timezone.datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    end = start + timedelta(days=1)

    rows = (
        NotificationLog.objects
        .filter(created_at__gte=start, created_at__lt=end)
        .values("template_id", "channel_type", "event_slug", "channel_id")
        .annotate(
            sent=Count("id", filter=~Q(status=DeliveryStatus.SUPPRESSED)),
            delivered=Count("id", filter=Q(status__in=[
                DeliveryStatus.DELIVERED, DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            opened=Count("id", filter=Q(status__in=[
                DeliveryStatus.OPENED, DeliveryStatus.CLICKED
            ])),
            clicked=Count("id", filter=Q(status=DeliveryStatus.CLICKED)),
            bounced=Count("id", filter=Q(status=DeliveryStatus.BOUNCED)),
            soft_bounced=Count("id", filter=Q(status=DeliveryStatus.SOFT_BOUNCED)),
            failed=Count("id", filter=Q(status=DeliveryStatus.FAILED)),
            suppressed=Count("id", filter=Q(status=DeliveryStatus.SUPPRESSED)),
            unsubscribed=Count("id", filter=Q(status=DeliveryStatus.UNSUBSCRIBED)),
            spam=Count("id", filter=Q(status=DeliveryStatus.SPAM)),
            total=Count("id"),
        )
    )

    built = 0
    for row in rows:
        summary, _ = NotificationDailySummary.objects.update_or_create(
            date=target_date,
            channel_type=row["channel_type"],
            template_id=row["template_id"],
            event_slug=row["event_slug"] or "",
            defaults={
                "channel_id": row["channel_id"],
                "sent_count": row["sent"] or 0,
                "delivered_count": row["delivered"] or 0,
                "opened_count": row["opened"] or 0,
                "clicked_count": row["clicked"] or 0,
                "bounced_count": row["bounced"] or 0,
                "soft_bounced_count": row["soft_bounced"] or 0,
                "failed_count": row["failed"] or 0,
                "suppressed_count": row["suppressed"] or 0,
                "unsubscribed_count": row["unsubscribed"] or 0,
                "spam_count": row["spam"] or 0,
                "total_jobs": row["total"] or 0,
                "is_partial": False,
            },
        )
        summary.compute_rates()
        built += 1

    logger.info("Built %d daily summary record(s) for %s", built, target_date)
    return built


def _get_deliverability_recommendations(bounce_rate: float, spam_rate: float) -> list:
    recs = []
    if bounce_rate > 5:
        recs.append("CRITICAL: Hard bounce rate above 5%. Immediate list hygiene required.")
    elif bounce_rate > 2:
        recs.append("WARNING: Hard bounce rate above 2%. Review list quality.")
    if spam_rate > 0.3:
        recs.append("CRITICAL: Spam rate above 0.3%. Check sending frequency and content.")
    elif spam_rate > 0.08:
        recs.append("WARNING: Spam rate above 0.08%. Investigate audience targeting.")
    if not recs:
        recs.append("Deliverability is within healthy thresholds.")
    return recs


# ══════════════════════════════════════════════════════════════
# MODULE: dashboard.py
# ══════════════════════════════════════════════════════════════

def get_notifications_dashboard_kpis(period_days: int = 30) -> dict:
    """
    All KPI cards for the Notifications dashboard tab.

    Returns dict with cards for: total sent, delivery rate, open rate,
    bounce rate, spam rate, suppressed, active channels, active webhooks.
    """
    from notifications.models import NotificationLog, NotificationChannel, WebhookEndpoint

    now = timezone.now()
    period_start = now - timedelta(days=period_days)
    prev_start = period_start - timedelta(days=period_days)

    current = get_delivery_stats(period_start, now)
    previous = get_delivery_stats(prev_start, period_start)

    def _block(curr_val, prev_val, fmt="number"):
        change = 0.0
        if prev_val and float(prev_val) != 0:
            change = round((float(curr_val) - float(prev_val)) / float(prev_val) * 100, 1)
        trend = "up" if change > 0 else "down" if change < 0 else "flat"
        return {
            "value": curr_val,
            "previous": prev_val,
            "change_pct": change,
            "trend": trend,
            "format": fmt,
        }

    active_channels = NotificationChannel.objects.filter(
        status=NotificationChannel.ChannelStatus.ACTIVE
    ).count()
    degraded_channels = NotificationChannel.objects.filter(
        status=NotificationChannel.ChannelStatus.DEGRADED
    ).count()
    active_webhooks = WebhookEndpoint.objects.filter(
        status=WebhookEndpoint.EndpointStatus.ACTIVE
    ).count()
    suspended_webhooks = WebhookEndpoint.objects.filter(
        status=WebhookEndpoint.EndpointStatus.SUSPENDED
    ).count()

    return {
        "period_days": period_days,
        "total_sent": _block(current["sent"], previous["sent"], "integer"),
        "delivery_rate": _block(current["delivery_rate"], previous["delivery_rate"], "percentage"),
        "open_rate": _block(current["open_rate"], previous["open_rate"], "percentage"),
        "click_rate": _block(current["click_rate"], previous["click_rate"], "percentage"),
        "bounce_rate": _block(current["bounce_rate"], previous["bounce_rate"], "percentage"),
        "spam_rate": _block(current["spam_rate"], previous["spam_rate"], "percentage"),
        "suppressed": current["suppressed"],
        "unsubscribed": current["unsubscribed"],
        "active_channels": active_channels,
        "degraded_channels": degraded_channels,
        "active_webhooks": active_webhooks,
        "suspended_webhooks": suspended_webhooks,
    }


def get_channel_status_overview() -> list:
    """All channels with their live health status."""
    from notifications.models import NotificationChannel
    from .channels_templates_prefs_webhooks_inapp import get_channel_health

    channels = NotificationChannel.objects.all().order_by("channel_type", "-is_default")
    return [
        {
            "id": str(ch.id),
            "name": ch.name,
            "channel_type": ch.channel_type,
            "status": ch.status,
            "is_operational": ch.is_operational,
            "consecutive_failures": ch.consecutive_failures,
            "daily_sends": ch.daily_send_count,
            "daily_limit": ch.rate_limit_per_day,
            "last_success": ch.last_successful_send_at.isoformat() if ch.last_successful_send_at else None,
        }
        for ch in channels
    ]


def get_recent_delivery_activity(limit: int = 20) -> list:
    """Recent notification logs for the dashboard activity feed."""
    from notifications.models import NotificationLog

    logs = (
        NotificationLog.objects
        .select_related("template")
        .order_by("-created_at")[:limit]
    )

    return [
        {
            "id": str(log.id),
            "event_slug": log.event_slug,
            "channel_type": log.channel_type,
            "recipient": log.recipient_address[:30] + ("..." if len(log.recipient_address) > 30 else ""),
            "status": log.status,
            "template_name": log.template.name if log.template else "",
            "created_at": log.created_at.isoformat(),
            "sent_at": log.sent_at.isoformat() if log.sent_at else None,
        }
        for log in logs
    ]


def get_notifications_health_checks() -> list:
    """
    Configuration and operational health checks for the notification system.
    """
    from notifications.models import (
        NotificationChannel, NotificationTemplate, WebhookEndpoint,
        NotificationBlacklist, NotificationDailySummary,
    )

    checks = []
    now = timezone.now()

    # ── At least one active email channel ──
    has_email = NotificationChannel.objects.filter(
        channel_type="email", status="active"
    ).exists()
    checks.append({
        "check": "email_channel",
        "status": "ok" if has_email else "error",
        "message": "Active email channel configured." if has_email
                   else "No active email channel. Email notifications will fail.",
    })

    # ── No degraded channels ──
    degraded = NotificationChannel.objects.filter(status="degraded").count()
    checks.append({
        "check": "degraded_channels",
        "status": "warning" if degraded > 0 else "ok",
        "message": f"{degraded} channel(s) are DEGRADED and may not be sending." if degraded
                   else "All channels are healthy.",
    })

    # ── Critical templates covered ──
    critical_events = [
        "order.placed", "order.shipped", "password.reset", "account.created"
    ]
    missing_templates = []
    for event in critical_events:
        if not NotificationTemplate.objects.filter(
            event_slug=event, channel_type="email", status="active", is_enabled=True
        ).exists():
            missing_templates.append(event)

    checks.append({
        "check": "critical_templates",
        "status": "warning" if missing_templates else "ok",
        "message": f"Missing active email templates for: {', '.join(missing_templates)}" if missing_templates
                   else "All critical email templates are configured.",
    })

    # ── Bounce rate alert ──
    yesterday = now - timedelta(days=1)
    from notifications.models import NotificationLog, BounceRecord, DeliveryStatus
    sent_24h = NotificationLog.objects.filter(
        created_at__gte=yesterday, channel_type="email"
    ).exclude(status=DeliveryStatus.SUPPRESSED).count()

    bounces_24h = BounceRecord.objects.filter(
        created_at__gte=yesterday, bounce_type="hard"
    ).count()

    bounce_rate = round(bounces_24h / sent_24h * 100, 2) if sent_24h > 0 else 0.0
    checks.append({
        "check": "bounce_rate_24h",
        "status": "error" if bounce_rate > 5 else "warning" if bounce_rate > 2 else "ok",
        "message": f"24h hard bounce rate: {bounce_rate}%" + (
            " — immediate action required!" if bounce_rate > 5
            else " — review list quality." if bounce_rate > 2
            else " — within healthy range."
        ),
    })

    # ── Suspended webhooks ──
    suspended_wh = WebhookEndpoint.objects.filter(status="suspended").count()
    checks.append({
        "check": "suspended_webhooks",
        "status": "warning" if suspended_wh > 0 else "ok",
        "message": f"{suspended_wh} webhook endpoint(s) are SUSPENDED due to repeated failures." if suspended_wh
                   else "All webhook endpoints are operational.",
    })

    # ── Blacklist size ──
    bl_count = NotificationBlacklist.objects.count()
    checks.append({
        "check": "blacklist_size",
        "status": "info",
        "message": f"{bl_count:,} address(es) on the suppression blacklist.",
    })

    return checks


def get_deliverability_alerts() -> list:
    """
    Active deliverability alerts requiring immediate attention.
    Checks bounce rates, spam rates, degraded channels.
    """
    from notifications.models import (
        NotificationChannel, BounceRecord, SpamComplaint, NotificationLog,
        DeliveryStatus,
    )

    alerts = []
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_hour = now - timedelta(hours=1)

    # Degraded channels
    for ch in NotificationChannel.objects.filter(status="degraded"):
        alerts.append({
            "severity": "error",
            "type": "degraded_channel",
            "title": f"Channel Degraded: {ch.name}",
            "message": f"{ch.consecutive_failures} consecutive failures. Last success: "
                       f"{ch.last_successful_send_at.strftime('%H:%M') if ch.last_successful_send_at else 'Never'}",
            "channel_id": str(ch.id),
        })

    # High bounce rate in last hour
    sent_1h = NotificationLog.objects.filter(
        created_at__gte=last_hour, channel_type="email"
    ).exclude(status=DeliveryStatus.SUPPRESSED).count()

    if sent_1h > 10:
        bounces_1h = BounceRecord.objects.filter(
            created_at__gte=last_hour, bounce_type="hard"
        ).count()
        if sent_1h > 0:
            rate = bounces_1h / sent_1h * 100
            if rate > 5:
                alerts.append({
                    "severity": "critical",
                    "type": "high_bounce_rate",
                    "title": "Critical Bounce Rate",
                    "message": f"Hard bounce rate is {rate:.1f}% in the last hour ({bounces_1h}/{sent_1h}).",
                })

    # Spam complaints spike
    spam_24h = SpamComplaint.objects.filter(created_at__gte=last_24h).count()
    if spam_24h >= 3:
        alerts.append({
            "severity": "warning",
            "type": "spam_complaints",
            "title": "Spam Complaints Spike",
            "message": f"{spam_24h} spam complaint(s) received in the last 24 hours.",
        })

    return alerts


def get_webhook_queue_status() -> dict:
    """Webhook delivery queue status for the dashboard."""
    from notifications.models import WebhookDeliveryAttempt, WebhookEndpoint

    now = timezone.now()

    pending_retries = WebhookDeliveryAttempt.objects.filter(
        is_successful=False,
        is_final_attempt=False,
        next_retry_at__isnull=False,
    ).count()

    due_now = WebhookDeliveryAttempt.objects.filter(
        is_successful=False,
        is_final_attempt=False,
        next_retry_at__lte=now,
    ).count()

    permanently_failed = WebhookDeliveryAttempt.objects.filter(
        is_successful=False,
        is_final_attempt=True,
        created_at__gte=now - timedelta(hours=24),
    ).count()

    suspended = WebhookEndpoint.objects.filter(status="suspended").count()

    return {
        "pending_retries": pending_retries,
        "due_now": due_now,
        "permanently_failed_24h": permanently_failed,
        "suspended_endpoints": suspended,
        "total_issues": pending_retries + suspended,
    }


def get_inapp_notification_queue(audience: str = "merchant") -> dict:
    """Current state of in-app notifications for the management panel."""
    from notifications.models import InAppNotification

    now = timezone.now()

    active = InAppNotification.objects.filter(
        audience=audience, is_active=True,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).count()

    pinned = InAppNotification.objects.filter(
        audience=audience, is_active=True, is_pinned=True,
    ).count()

    expiring_soon = InAppNotification.objects.filter(
        audience=audience, is_active=True,
        expires_at__gte=now, expires_at__lte=now + timedelta(hours=24),
    ).count()

    recent = list(
        InAppNotification.objects.filter(audience=audience)
        .order_by("-created_at")[:10]
        .values("id", "title", "notification_type", "is_active", "is_pinned",
                "created_at", "expires_at")
    )

    return {
        "active_notifications": active,
        "pinned_notifications": pinned,
        "expiring_24h": expiring_soon,
        "recent": recent,
    }


def get_template_coverage_report() -> dict:
    """
    Report on which critical events have templates configured.
    Shows gaps in notification coverage.
    """
    from notifications.models import NotificationTemplate

    critical_events = {
        "order.placed": "Order Confirmation",
        "order.shipped": "Shipment Notification",
        "order.delivered": "Delivery Confirmation",
        "order.cancelled": "Order Cancellation",
        "order.refunded": "Refund Confirmation",
        "password.reset": "Password Reset",
        "account.created": "Welcome / Account Created",
        "cart.abandoned": "Abandoned Cart Recovery",
        "payment.failed": "Payment Failed",
        "return.requested": "Return Confirmation",
    }

    covered = []
    missing = []

    for event_slug, label in critical_events.items():
        has_email = NotificationTemplate.objects.filter(
            event_slug=event_slug, channel_type="email",
            status="active", is_enabled=True
        ).exists()

        covered_channels = list(
            NotificationTemplate.objects.filter(
                event_slug=event_slug, status="active", is_enabled=True
            ).values_list("channel_type", flat=True)
        )

        entry = {
            "event_slug": event_slug,
            "label": label,
            "covered_channels": covered_channels,
            "has_email": has_email,
        }

        if has_email:
            covered.append(entry)
        else:
            missing.append(entry)

    return {
        "total_critical_events": len(critical_events),
        "covered": len(covered),
        "missing": len(missing),
        "coverage_pct": round(len(covered) / len(critical_events) * 100, 1),
        "covered_events": covered,
        "missing_events": missing,
    }


def get_suppression_stats() -> dict:
    """Blacklist/suppression list statistics."""
    from notifications.models import NotificationBlacklist

    by_type = list(
        NotificationBlacklist.objects
        .values("entry_type", "reason")
        .annotate(count=Count("id"))
        .order_by("entry_type", "-count")
    )

    total = NotificationBlacklist.objects.count()
    permanent = NotificationBlacklist.objects.filter(expires_at__isnull=True).count()
    temporary = total - permanent

    return {
        "total": total,
        "permanent": permanent,
        "temporary": temporary,
        "by_type_and_reason": by_type,
    }


def get_notifications_attention_queue() -> dict:
    """All items needing staff attention across the notifications domain."""
    from notifications.models import NotificationChannel, WebhookEndpoint, NotificationJob

    now = timezone.now()

    degraded_channels = NotificationChannel.objects.filter(status="degraded").count()
    suspended_webhooks = WebhookEndpoint.objects.filter(status="suspended").count()
    failed_jobs_24h = NotificationJob.objects.filter(
        status="failed",
        updated_at__gte=now - timedelta(hours=24),
    ).count()
    pending_webhook_retries = NotificationJob.objects.filter(
        status="queued",
        channel_type="webhook",
        next_attempt_at__lte=now,
    ).count()

    deliverability = get_deliverability_health(
        now - timedelta(hours=24), now
    )

    total = (
        degraded_channels + suspended_webhooks +
        int(deliverability["health_status"] == "critical") +
        int(deliverability["health_status"] == "warning")
    )

    return {
        "total_issues": total,
        "degraded_channels": degraded_channels,
        "suspended_webhooks": suspended_webhooks,
        "failed_jobs_24h": failed_jobs_24h,
        "pending_webhook_retries": pending_webhook_retries,
        "deliverability_status": deliverability["health_status"],
        "bounce_rate_24h": deliverability["hard_bounce_rate"],
        "spam_rate_24h": deliverability["spam_rate"],
        "recommendations": deliverability["recommendations"],
    }
