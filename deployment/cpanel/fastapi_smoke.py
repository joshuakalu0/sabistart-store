from __future__ import annotations

import os
import socket
import sys
from datetime import datetime, timezone

from fastapi import FastAPI


app = FastAPI(title="SabiStart cPanel Smoke Test")


@app.get("/")
def index() -> dict[str, object]:
    return {
        "ok": True,
        "message": "FastAPI smoke server is running.",
        "time": datetime.now(timezone.utc).isoformat(),
        "python": sys.executable,
        "cwd": os.getcwd(),
        "host": socket.gethostname(),
    }


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}

