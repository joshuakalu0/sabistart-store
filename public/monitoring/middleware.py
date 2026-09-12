from __future__ import annotations

from public.monitoring.services import (
    begin_request_timer,
    ensure_visitor_session,
    record_page_visit,
    should_track_request,
)


import logging

from django.db import connection

logger = logging.getLogger(__name__)

# Paths that should never be tracked (platform admin, static assets, etc.)
_SKIP_MONITORING_PREFIXES = (
    "/platform/",
    "/admin/",
    "/static/",
    "/media/",
    "/favicon",
    "/healthz",
    "/readyz",
)


class VisitorMonitoringMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip monitoring on public schema (platform pages) — no tenant visit tables here.
        # Also skip well-known platform paths regardless of schema.
        schema = getattr(connection, "schema_name", "public")
        path = request.path
        if schema == "public" or any(path.startswith(p) for p in _SKIP_MONITORING_PREFIXES):
            return self.get_response(request)

        headers = dict(request.headers)
        tracked = False
        try:
            if should_track_request(path, request.method, headers):
                if hasattr(request, "session") and not request.session.session_key:
                    request.session.create()
                request._visitor_monitoring_session = ensure_visitor_session(request)
                begin_request_timer(request)
                tracked = True
        except Exception as exc:
            logger.debug("Visitor monitoring pre-request error: %s", exc)

        response = self.get_response(request)

        if tracked:
            try:
                record_page_visit(request, response)
            except Exception as exc:
                logger.debug("Visitor monitoring post-request error: %s", exc)

        return response
