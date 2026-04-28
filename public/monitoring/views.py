from __future__ import annotations

import json

from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from public.monitoring.services import update_visit_from_beacon
from public.utils import rate_limit


@csrf_exempt
@require_POST
@rate_limit(rate=120, per_seconds=60, scope="monitoring_beacon", by_user=False)
def beacon(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid beacon payload.")

    visit = update_visit_from_beacon(
        visit_id=str(payload.get("visit_id") or "").strip(),
        session_key=getattr(request.session, "session_key", "") or "",
        path=str(payload.get("path") or request.path or ""),
        payload=payload,
    )
    if visit is None:
        return JsonResponse({"ok": False, "updated": False}, status=404)
    return JsonResponse({"ok": True, "updated": True, "visit_id": str(visit.id)})
