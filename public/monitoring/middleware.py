from __future__ import annotations

from public.monitoring.services import (
    begin_request_timer,
    ensure_visitor_session,
    record_page_visit,
    should_track_request,
)


class VisitorMonitoringMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        headers = dict(request.headers)
        if should_track_request(request.path, request.method, headers):
            if not request.session.session_key:
                request.session.create()
            request._visitor_monitoring_session = ensure_visitor_session(request)
            begin_request_timer(request)
        response = self.get_response(request)
        if should_track_request(request.path, request.method, headers):
            record_page_visit(request, response)
        return response
