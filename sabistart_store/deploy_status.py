from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse


def deployz(request):
    marker_path = Path(settings.BASE_DIR) / "tmp" / "deploy.json"
    marker: dict[str, object] = {}

    if marker_path.exists():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            marker = {"marker_error": "deploy marker could not be read"}

    payload = {
        "ok": True,
        "message": "SabiStart Django app is being served by Passenger.",
        "host": request.get_host(),
        "base_dir": str(settings.BASE_DIR),
        "python": sys.executable,
        "env_file": os.environ.get("SABISTART_ENV_FILE", ""),
        "marker": marker,
    }
    return JsonResponse(payload)
