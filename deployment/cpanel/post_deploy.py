from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXECUTABLE = sys.executable


def run(*args: str) -> None:
    subprocess.run(args, cwd=APP_ROOT, check=True)


def ensure_runtime_directories() -> None:
    sys.path.insert(0, str(APP_ROOT))
    from sabistart_store.env import load_environment

    load_environment()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sabistart_store.settings")

    from django.conf import settings

    paths = [
        Path(settings.STATIC_ROOT),
        Path(settings.MEDIA_ROOT),
        Path(getattr(settings, "LOG_DIR", settings.BASE_DIR / "logs")),
        Path(settings.BASE_DIR / "tmp"),
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def ensure_database_connection() -> None:
    sys.path.insert(0, str(APP_ROOT))
    from sabistart_store.env import load_environment

    load_environment()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sabistart_store.settings")

    import django
    from django.conf import settings
    from django.db import connection
    from django.db.utils import OperationalError

    django.setup()

    try:
        connection.ensure_connection()
    except OperationalError as exc:
        db_settings = settings.DATABASES["default"]
        host = db_settings.get("HOST") or "unknown-host"
        port = db_settings.get("PORT") or "5432"
        engine = db_settings.get("ENGINE") or "unknown-engine"

        message = [
            "Database connection preflight failed before migrations.",
            f"Configured engine: {engine}",
            f"Configured host: {host}",
            f"Configured port: {port}",
            "",
            "Common causes on cPanel:",
            "1. The hosting provider blocks outbound PostgreSQL connections to external services.",
            "2. The database host/port is wrong.",
            "3. SSL is required but the connection settings do not match the provider.",
            "4. The remote PostgreSQL service is paused, offline, or refusing direct connections.",
        ]

        if "neon.tech" in str(host):
            message.extend(
                [
                    "",
                    "Neon-specific note:",
                    "- If this cPanel host cannot reach Neon on port 5432, the app itself will not work from this host.",
                    "- Prefer local cPanel PostgreSQL for this deployment, or confirm the host allows outbound access to Neon.",
                    "- If you intentionally use Neon, verify whether the pooled and direct URLs are both reachable from the cPanel server.",
                ]
            )

        message.extend(
            [
                "",
                "Original database error:",
                str(exc),
            ]
        )
        raise RuntimeError("\n".join(message)) from exc


def main() -> None:
    print(f"Using Python: {PYTHON_EXECUTABLE}")
    run(PYTHON_EXECUTABLE, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt")
    run(PYTHON_EXECUTABLE, "manage.py", "check")
    run(PYTHON_EXECUTABLE, "manage.py", "check_cpanel_deployment", "--strict")
    ensure_runtime_directories()
    ensure_database_connection()
    run(PYTHON_EXECUTABLE, "manage.py", "migrate_schemas", "--shared", "--noinput")
    run(PYTHON_EXECUTABLE, "manage.py", "migrate_schemas", "--tenant", "--noinput")
    run(PYTHON_EXECUTABLE, "manage.py", "sync_theme_catalog")
    run(PYTHON_EXECUTABLE, "manage.py", "sync_domain_tld_catalog")
    run(PYTHON_EXECUTABLE, "manage.py", "collectstatic", "--noinput")

    tmp_dir = APP_ROOT / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / "restart.txt").touch()

    print("cPanel post-deploy finished successfully.")


if __name__ == "__main__":
    main()
