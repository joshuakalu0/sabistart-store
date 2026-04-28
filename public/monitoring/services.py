from __future__ import annotations

from datetime import timedelta
import logging
from time import perf_counter

from django.db.models import Avg, Count, Max
from django.db import connection
from django.db.models.functions import TruncDate
from django.urls import resolve, Resolver404
from django.utils import timezone

from public.monitoring.models import PageVisit, VisitorSession
from public.utils import get_client_ip


logger = logging.getLogger(__name__)

TRACKABLE_PREFIXES = ("", "/dashboard/", "/platform/", "/account/")
SKIP_PREFIXES = ("/static/", "/media/", "/favicon", "/admin/jsi18n/")
SKIP_SUFFIXES = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2")


def classify_request_source(path: str) -> str:
    normalized = path or "/"
    if normalized.startswith("/dashboard/"):
        return VisitorSession.Source.DASHBOARD
    if normalized.startswith("/platform/"):
        return VisitorSession.Source.PLATFORM
    return VisitorSession.Source.STOREFRONT


def should_track_request(path: str, method: str = "GET", headers: dict | None = None) -> bool:
    if method.upper() not in {"GET", "HEAD"}:
        return False
    # Skip AJAX/XHR requests – these are API calls, not page visits
    if headers and (
        headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (headers.get("Accept") or "")
    ):
        return False
    if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    if path.endswith(SKIP_SUFFIXES):
        return False
    return any(path.startswith(prefix) for prefix in TRACKABLE_PREFIXES)


def is_probable_bot(user_agent: str) -> bool:
    normalized = (user_agent or "").lower()
    markers = ("bot", "crawl", "spider", "preview", "monitor", "uptime")
    return any(marker in normalized for marker in markers)


def ensure_visitor_session(request):
    session_key = request.session.session_key or ""
    schema_name = getattr(connection, "schema_name", "public")
    user_identifier = ""
    if getattr(request.user, "is_authenticated", False):
        user_identifier = str(getattr(request.user, "pk", "")) or getattr(request.user, "email", "") or ""

    defaults = {
        "schema_name": schema_name,
        "source": classify_request_source(request.path),
        "user_identifier": user_identifier,
        "ip_address": get_client_ip(request) or None,
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:1000],
        "referrer": request.META.get("HTTP_REFERER", "")[:500],
        "landing_path": request.path[:500],
        "last_path": request.path[:500],
        "is_bot": is_probable_bot(request.META.get("HTTP_USER_AGENT", "")),
        "last_seen_at": timezone.now(),
    }
    visitor_session, created = VisitorSession.objects.get_or_create(
        session_key=session_key or f"anon:{schema_name}",
        schema_name=schema_name,
        defaults=defaults,
    )
    if not created:
        visitor_session.source = defaults["source"]
        visitor_session.user_identifier = user_identifier or visitor_session.user_identifier
        visitor_session.ip_address = defaults["ip_address"] or visitor_session.ip_address
        visitor_session.user_agent = defaults["user_agent"] or visitor_session.user_agent
        visitor_session.referrer = defaults["referrer"] or visitor_session.referrer
        visitor_session.last_path = request.path[:500]
        visitor_session.last_seen_at = timezone.now()
        visitor_session.visit_count = visitor_session.visit_count + 1
        visitor_session.save(
            update_fields=[
                "source",
                "user_identifier",
                "ip_address",
                "user_agent",
                "referrer",
                "last_path",
                "last_seen_at",
                "visit_count",
            ]
        )
    else:
        visitor_session.visit_count = 1
        visitor_session.save(update_fields=["visit_count"])
    return visitor_session


def begin_request_timer(request):
    request._monitoring_started_at = perf_counter()


def record_page_visit(request, response):
    if not hasattr(request, "_monitoring_started_at"):
        return None
    visitor_session = getattr(request, "_visitor_monitoring_session", None)
    if visitor_session is None:
        return None
    elapsed_ms = max(int((perf_counter() - request._monitoring_started_at) * 1000), 0)
    try:
        match = resolve(request.path)
        route_name = match.view_name or ""
    except Resolver404:
        route_name = ""

    try:
        visit = PageVisit.objects.create(
            visitor_session=visitor_session,
            schema_name=visitor_session.schema_name,
            source=visitor_session.source,
            path=request.path[:500],
            full_url=request.build_absolute_uri()[:1000],
            route_name=route_name[:255],
            method=request.method[:10],
            referrer=(request.META.get("HTTP_REFERER", "") or "")[:500],
            status_code=getattr(response, "status_code", 200),
            server_duration_ms=elapsed_ms,
            metadata={},
        )
        request._page_visit_id = str(visit.id)
        return visit
    except Exception:
        logger.debug("PageVisit recording failed (non-fatal)", exc_info=True)
        return None


def update_visit_from_beacon(*, visit_id: str = "", session_key: str = "", path: str = "", payload: dict):
    visit = None
    if visit_id:
        visit = PageVisit.objects.filter(pk=visit_id).first()
    if visit is None and session_key:
        queryset = PageVisit.objects.filter(
            visitor_session__session_key=session_key,
        )
        if path:
            queryset = queryset.filter(path=path[:500])
        visit = queryset.order_by("-created_at").first()
    if not visit:
        return None
    metadata = dict(visit.metadata or {})
    metadata["client"] = {
        "screen": payload.get("screen", {}),
        "timezone": payload.get("timezone", ""),
        "language": payload.get("language", ""),
        "visibility_state": payload.get("visibility_state", ""),
    }
    visit.client_duration_ms = max(int(payload.get("duration_ms") or 0), 0)
    visit.engaged_seconds = max(int(payload.get("engaged_seconds") or 0), 0)
    visit.page_title = str(payload.get("title") or "")[:255]
    visit.metadata = metadata
    visit.save(update_fields=["client_duration_ms", "engaged_seconds", "page_title", "metadata"])
    return visit


def _window_start(days: int):
    safe_days = max(int(days or 1), 1)
    return timezone.now() - timedelta(days=safe_days)


def _page_visit_queryset(*, days: int = 14, source: str = ""):
    queryset = PageVisit.objects.select_related("visitor_session").filter(created_at__gte=_window_start(days))
    if source:
        queryset = queryset.filter(source=source)
    return queryset


def _visitor_session_queryset(*, days: int = 14, source: str = ""):
    queryset = VisitorSession.objects.filter(last_seen_at__gte=_window_start(days))
    if source:
        queryset = queryset.filter(source=source)
    return queryset


def _build_daily_series(rows, *, days: int):
    total_days = max(int(days or 1), 1)
    start_date = timezone.localdate() - timedelta(days=total_days - 1)
    row_map = {row["day"]: row for row in rows}
    series = []
    highest_views = 0
    for offset in range(total_days):
        current_day = start_date + timedelta(days=offset)
        current = row_map.get(current_day, {})
        views = int(current.get("views") or 0)
        sessions = int(current.get("sessions") or 0)
        avg_server_duration_ms = int(current.get("avg_server_duration_ms") or 0)
        highest_views = max(highest_views, views)
        series.append(
            {
                "day": current_day,
                "label": current_day.strftime("%b %d"),
                "views": views,
                "sessions": sessions,
                "avg_server_duration_ms": avg_server_duration_ms,
            }
        )
    highest_views = highest_views or 1
    for row in series:
        row["view_width_percent"] = round((row["views"] / highest_views) * 100, 2) if row["views"] else 0
    return series


def build_monitoring_dashboard_snapshot(*, days: int = 14, source: str = "") -> dict:
    page_visits = _page_visit_queryset(days=days, source=source)
    visitor_sessions = _visitor_session_queryset(days=days, source=source)

    totals = page_visits.aggregate(
        average_server_duration_ms=Avg("server_duration_ms"),
        average_client_duration_ms=Avg("client_duration_ms"),
        average_engaged_seconds=Avg("engaged_seconds"),
    )
    unique_known_users = (
        visitor_sessions.exclude(user_identifier="")
        .values("user_identifier")
        .distinct()
        .count()
    )

    source_breakdown = list(
        page_visits.values("source")
        .annotate(
            views=Count("id"),
            sessions=Count("visitor_session", distinct=True),
        )
        .order_by("-views", "source")
    )
    daily_rows = list(
        page_visits.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            views=Count("id"),
            sessions=Count("visitor_session", distinct=True),
            avg_server_duration_ms=Avg("server_duration_ms"),
        )
        .order_by("day")
    )
    top_pages = list(
        page_visits.values("path")
        .annotate(
            views=Count("id"),
            sessions=Count("visitor_session", distinct=True),
            avg_server_duration_ms=Avg("server_duration_ms"),
            avg_engaged_seconds=Avg("engaged_seconds"),
            last_seen_at=Max("created_at"),
        )
        .order_by("-views", "path")[:15]
    )
    top_referrers = list(
        page_visits.exclude(referrer="")
        .values("referrer")
        .annotate(views=Count("id"))
        .order_by("-views", "referrer")[:10]
    )
    recent_visits = list(page_visits.order_by("-created_at")[:20])
    active_sessions = list(visitor_sessions.order_by("-last_seen_at")[:20])

    return {
        "days": max(int(days or 1), 1),
        "source": source,
        "total_page_views": page_visits.count(),
        "total_sessions": visitor_sessions.count(),
        "unique_known_users": unique_known_users,
        "average_server_duration_ms": int(totals["average_server_duration_ms"] or 0),
        "average_client_duration_ms": int(totals["average_client_duration_ms"] or 0),
        "average_engaged_seconds": int(totals["average_engaged_seconds"] or 0),
        "source_breakdown": source_breakdown,
        "daily_series": _build_daily_series(daily_rows, days=days),
        "top_pages": top_pages,
        "top_referrers": top_referrers,
        "recent_visits": recent_visits,
        "active_sessions": active_sessions,
    }
