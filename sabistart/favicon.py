from __future__ import annotations

from django.http import HttpResponse


def favicon(request):
    return HttpResponse(status=204)
