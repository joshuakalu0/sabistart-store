from django.db import connection
from django.http import JsonResponse
from django.utils import timezone


def healthz(request):
    return JsonResponse(
        {
            "status": "ok",
            "timestamp": timezone.now().isoformat(),
        }
    )


def readyz(request):
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        db_ok = False
    return JsonResponse(
        {
            "status": "ok" if db_ok else "error",
            "database": "ok" if db_ok else "error",
            "timestamp": timezone.now().isoformat(),
        },
        status=200 if db_ok else 503,
    )
