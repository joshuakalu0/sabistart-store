from __future__ import annotations

from public.monitoring.services import (
    begin_request_timer,
    ensure_visitor_session,
    record_page_visit,
    should_track_request,
)


import logging

logger = logging.getLogger(__name__)


class VisitorMonitoringMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        headers = dict(request.headers)
        tracked = False
        try:
            if should_track_request(request.path, request.method, headers):
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
