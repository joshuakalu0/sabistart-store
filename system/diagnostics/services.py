"""
system/diagnostics/services.py
================================
Platform-level diagnostic checks. Every check returns a standardised dict and
MUST NEVER raise an unhandled exception.

Result schema
-------------
{
    "name":       str,   # short check identifier
    "label":      str,   # human-friendly label
    "status":     str,   # "ok" | "warning" | "error" | "unknown"
    "message":    str,   # one-line summary
    "detail":     str,   # verbose detail / error trace
    "latency_ms": int,   # wall-clock ms this check took
}
"""
from __future__ import annotations

import smtplib
import socket
import sys
import time
import traceback
from typing import Any


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _check(name: str, label: str):
    """Return a blank result skeleton."""
    return {
        "name": name,
        "label": label,
        "status": "unknown",
        "message": "Not yet run.",
        "detail": "",
        "latency_ms": 0,
    }


def _ok(r: dict, message: str, detail: str = "") -> dict:
    r.update(status="ok", message=message, detail=detail)
    return r


def _warn(r: dict, message: str, detail: str = "") -> dict:
    r.update(status="warning", message=message, detail=detail)
    return r


def _err(r: dict, message: str, detail: str = "") -> dict:
    r.update(status="error", message=message, detail=detail)
    return r


class _Timer:
    def __init__(self, result: dict):
        self._r = result
        self._start = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, *_):
        self._r["latency_ms"] = int((time.monotonic() - self._start) * 1000)


# ──────────────────────────────────────────────
# Section 1 – Payment Gateways
# ──────────────────────────────────────────────

def _check_paystack_credential() -> dict:
    r = _check("paystack_credential", "Paystack: Credential config")
    with _Timer(r):
        try:
            from system.system_pay.models import PaymentGatewayDefinition, PlatformGatewayCredential
            gw = PaymentGatewayDefinition.objects.filter(provider="paystack").first()
            if not gw:
                return _warn(r, "Paystack gateway definition not found in DB.")
            if not gw.is_enabled:
                return _warn(r, f"Paystack ({gw.name}) is defined but NOT enabled on the platform.")
            cred = gw.platform_credentials.filter(is_active=True).order_by("-priority").first()
            if not cred:
                return _err(r, "No active PlatformGatewayCredential for Paystack.")
            env = cred.environment
            has_secret = bool(cred.secret_key and cred.secret_key.strip())
            if not has_secret:
                return _err(r, f"Paystack credential ({cred.name}) has no secret key.")
            return _ok(r, f"Paystack credential '{cred.name}' active ({env}).",
                       f"Priority {cred.priority}, last used: {cred.last_used_at or 'never'}")
        except Exception:
            return _err(r, "Exception checking Paystack credential.", traceback.format_exc())


def _check_paystack_connectivity() -> dict:
    r = _check("paystack_connectivity", "Paystack: API connectivity")
    with _Timer(r):
        try:
            from system.system_pay.models import PaymentGatewayDefinition
            from dashboard.payments_tenant.services.provider_checkout import _json_request
            gw = PaymentGatewayDefinition.objects.filter(provider="paystack").first()
            if not gw:
                return _warn(r, "Paystack not configured — skipping connectivity test.")
            cred = gw.platform_credentials.filter(is_active=True).order_by("-priority").first()
            if not cred or not cred.secret_key:
                return _warn(r, "No active Paystack secret key — skipping connectivity test.")
            secret = cred.secret_key.strip()
            # Intentionally bad payload: Paystack will return {status:false, message:"..."} not a Cloudflare block
            res = _json_request(
                "POST",
                "https://api.paystack.co/transaction/initialize",
                headers={"Authorization": f"Bearer {secret}"},
                json_body={"amount": 0, "email": "diag@sabistart.test"},
            )
            if isinstance(res, dict) and "<html" not in str(res.get("message", "")):
                # Either status=true (unlikely with 0) or status=false with a Paystack message = reachable
                status_val = res.get("status", False)
                msg = res.get("message", "")
                if "cloudflare" in str(msg).lower() or "1010" in str(msg):
                    return _err(r, "Blocked by Cloudflare (1010). Check server IP/User-Agent.", str(res))
                return _ok(r, f"Paystack API reachable. Response: {msg}", str(res))
            return _err(r, "Unexpected response from Paystack API.", str(res))
        except Exception:
            return _err(r, "Exception during Paystack connectivity test.", traceback.format_exc())


def _check_flutterwave_credential() -> dict:
    r = _check("flutterwave_credential", "Flutterwave: Credential config")
    with _Timer(r):
        try:
            from system.system_pay.models import PaymentGatewayDefinition
            gw = PaymentGatewayDefinition.objects.filter(provider="flutterwave").first()
            if not gw:
                return _warn(r, "Flutterwave gateway definition not found in DB.")
            if not gw.is_enabled:
                return _warn(r, f"Flutterwave ({gw.name}) is defined but NOT enabled on the platform.")
            cred = gw.platform_credentials.filter(is_active=True).order_by("-priority").first()
            if not cred:
                return _err(r, "No active PlatformGatewayCredential for Flutterwave.")
            has_secret = bool(cred.secret_key and cred.secret_key.strip())
            if not has_secret:
                return _err(r, f"Flutterwave credential ({cred.name}) has no secret key.")
            return _ok(r, f"Flutterwave credential '{cred.name}' active ({cred.environment}).",
                       f"Priority {cred.priority}, last used: {cred.last_used_at or 'never'}")
        except Exception:
            return _err(r, "Exception checking Flutterwave credential.", traceback.format_exc())


def _check_flutterwave_connectivity() -> dict:
    r = _check("flutterwave_connectivity", "Flutterwave: API connectivity")
    with _Timer(r):
        try:
            from system.system_pay.models import PaymentGatewayDefinition
            from dashboard.payments_tenant.services.provider_checkout import _json_request
            gw = PaymentGatewayDefinition.objects.filter(provider="flutterwave").first()
            if not gw:
                return _warn(r, "Flutterwave not configured — skipping connectivity test.")
            cred = gw.platform_credentials.filter(is_active=True).order_by("-priority").first()
            if not cred or not cred.secret_key:
                return _warn(r, "No active Flutterwave secret key — skipping connectivity test.")
            secret = cred.secret_key.strip()
            # Verify a non-existent transaction — expect a data/error response, not an auth error
            res = _json_request(
                "GET",
                "https://api.flutterwave.com/v3/transactions/0/verify",
                headers={"Authorization": f"Bearer {secret}"},
            )
            msg = res.get("message", "")
            status_val = res.get("status", "")
            if status_val == "error" and "authorization" in msg.lower():
                return _err(r, "Flutterwave authentication failed. Check secret key.", str(res))
            # Any structured JSON response = reachable
            return _ok(r, f"Flutterwave API reachable. Response: {msg}", str(res))
        except Exception:
            return _err(r, "Exception during Flutterwave connectivity test.", traceback.format_exc())


def _check_active_gateway() -> dict:
    r = _check("active_gateway", "Active platform gateway")
    with _Timer(r):
        try:
            from system.system_pay.models import PaymentGatewayDefinition
            gateways = list(PaymentGatewayDefinition.objects.filter(is_enabled=True).values("provider", "name"))
            if not gateways:
                return _warn(r, "No payment gateways are currently enabled on the platform.")
            names = ", ".join(f"{g['name']} ({g['provider']})" for g in gateways)
            return _ok(r, f"{len(gateways)} enabled gateway(s): {names}.")
        except Exception:
            return _err(r, "Exception checking active gateway.", traceback.format_exc())


def run_payment_diagnostics() -> list[dict]:
    return [
        _check_paystack_credential(),
        _check_paystack_connectivity(),
        _check_flutterwave_credential(),
        _check_flutterwave_connectivity(),
        _check_active_gateway(),
    ]


# ──────────────────────────────────────────────
# Section 2 – Email / SMTP
# ──────────────────────────────────────────────

def _check_django_email_settings() -> dict:
    r = _check("django_email_settings", "Django email backend settings")
    with _Timer(r):
        try:
            from django.conf import settings
            backend = getattr(settings, "EMAIL_BACKEND", "not set")
            host = getattr(settings, "EMAIL_HOST", "")
            port = getattr(settings, "EMAIL_PORT", 587)
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
            if "console" in backend:
                return _warn(r, "Console email backend is active — emails won't be delivered.",
                             f"Backend: {backend}")
            if "dummy" in backend:
                return _warn(r, "Dummy email backend is active — emails discarded.",
                             f"Backend: {backend}")
            detail = f"Backend: {backend}\nHost: {host}:{port}\nFrom: {from_email}"
            return _ok(r, f"Email backend: {backend.split('.')[-1]}", detail)
        except Exception:
            return _err(r, "Exception reading email settings.", traceback.format_exc())


def _check_smtp_connectivity() -> dict:
    r = _check("smtp_connectivity", "SMTP server TCP connectivity")
    with _Timer(r):
        try:
            from django.conf import settings
            host = getattr(settings, "EMAIL_HOST", "")
            port = getattr(settings, "EMAIL_PORT", 587)
            if not host:
                return _warn(r, "EMAIL_HOST not configured.")
            sock = socket.create_connection((host, port), timeout=10)
            sock.close()
            return _ok(r, f"SMTP server {host}:{port} is reachable.")
        except (socket.timeout, ConnectionRefusedError, OSError) as exc:
            return _err(r, f"Cannot reach SMTP server: {exc}",
                        traceback.format_exc())
        except Exception:
            return _err(r, "Exception during SMTP TCP connectivity test.", traceback.format_exc())


def _check_email_channel_configs() -> dict:
    r = _check("email_channel_configs", "Tenant email channel configurations")
    with _Timer(r):
        try:
            from dashboard.notification.models import EmailChannelConfig
            total = EmailChannelConfig.objects.count()
            if total == 0:
                return _warn(r, "No EmailChannelConfig records found in DB.")
            return _ok(r, f"{total} EmailChannelConfig record(s) in DB.")
        except Exception:
            return _err(r, "Exception querying EmailChannelConfig.", traceback.format_exc())


def run_email_diagnostics() -> list[dict]:
    return [
        _check_django_email_settings(),
        _check_smtp_connectivity(),
        _check_email_channel_configs(),
    ]


# ──────────────────────────────────────────────
# Section 3 – Messaging / WhatsApp / SMS
# ──────────────────────────────────────────────

def _check_whatsapp_channel() -> dict:
    r = _check("whatsapp_channel", "WhatsApp notification channel")
    with _Timer(r):
        try:
            from dashboard.notification.models import NotificationChannel
            whatsapp = NotificationChannel.objects.filter(channel_type="whatsapp")
            total = whatsapp.count()
            active = whatsapp.filter(is_active=True).count()
            if total == 0:
                return _warn(r, "No WhatsApp notification channels configured.")
            return _ok(r, f"{active}/{total} WhatsApp channel(s) active.",
                       f"Total: {total}, Active: {active}")
        except Exception:
            return _err(r, "Exception checking WhatsApp channel.", traceback.format_exc())


def _check_sms_channel() -> dict:
    r = _check("sms_channel", "SMS notification channel")
    with _Timer(r):
        try:
            from dashboard.notification.models import SMSChannelConfig
            total = SMSChannelConfig.objects.count()
            if total == 0:
                return _warn(r, "No SMSChannelConfig records found.")
            return _ok(r, f"{total} SMSChannelConfig record(s) in DB.")
        except Exception:
            return _err(r, "Exception checking SMS channel.", traceback.format_exc())


def _check_notification_channel_overview() -> dict:
    r = _check("notification_channels_overview", "Notification channels overview")
    with _Timer(r):
        try:
            from dashboard.notification.models import NotificationChannel
            from django.db.models import Count
            rows = (
                NotificationChannel.objects
                .values("channel_type")
                .annotate(total=Count("id"))
                .order_by("channel_type")
            )
            if not rows:
                return _warn(r, "No notification channels found in the database.")
            lines = [f"{row['channel_type']}: {row['total']}" for row in rows]
            return _ok(r, f"{len(lines)} channel type(s) configured.", "\n".join(lines))
        except Exception:
            return _err(r, "Exception querying notification channels.", traceback.format_exc())


def run_messaging_diagnostics() -> list[dict]:
    return [
        _check_whatsapp_channel(),
        _check_sms_channel(),
        _check_notification_channel_overview(),
    ]


# ──────────────────────────────────────────────
# Section 4 – Database
# ──────────────────────────────────────────────

def _check_db_connection() -> dict:
    r = _check("db_connection", "PostgreSQL connection (public schema)")
    with _Timer(r):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
            return _ok(r, "Database connection is healthy.", version)
        except Exception:
            return _err(r, "Database connection failed.", traceback.format_exc())


def _check_tenant_count() -> dict:
    r = _check("tenant_count", "Tenant / Shop count")
    with _Timer(r):
        try:
            from system.core.models import Shop
            count = Shop.objects.count()
            return _ok(r, f"{count} tenant schema(s) registered.")
        except Exception:
            return _err(r, "Exception counting tenants.", traceback.format_exc())


def _check_migration_status() -> dict:
    r = _check("migration_status", "Unapplied migrations")
    with _Timer(r):
        try:
            from django.db import connection
            from django.db.migrations.loader import MigrationLoader
            loader = MigrationLoader(connection)
            unapplied = [
                f"{app}.{name}"
                for (app, name) in loader.graph.leaf_nodes()
                if (app, name) not in loader.applied_migrations
            ]
            if unapplied:
                return _warn(r, f"{len(unapplied)} unapplied migration(s) detected.",
                             "\n".join(unapplied))
            return _ok(r, "All migrations are applied.")
        except Exception:
            return _err(r, "Exception checking migrations.", traceback.format_exc())


def _check_cache() -> dict:
    r = _check("cache_connectivity", "Cache / Redis connectivity")
    with _Timer(r):
        try:
            from django.core.cache import cache
            probe_key = "_diag_probe_"
            cache.set(probe_key, "ping", 10)
            val = cache.get(probe_key)
            cache.delete(probe_key)
            if val == "ping":
                return _ok(r, "Cache backend is working (set/get/delete succeeded).")
            return _warn(r, "Cache get returned unexpected value.", f"Got: {val!r}")
        except Exception:
            return _err(r, "Cache backend is unreachable or misconfigured.", traceback.format_exc())


def run_database_diagnostics() -> list[dict]:
    return [
        _check_db_connection(),
        _check_tenant_count(),
        _check_migration_status(),
        _check_cache(),
    ]


# ──────────────────────────────────────────────
# Section 5 – Storage / Media
# ──────────────────────────────────────────────

def _check_storage_backend() -> dict:
    r = _check("storage_backend", "File storage backend")
    with _Timer(r):
        try:
            from django.conf import settings
            storages = getattr(settings, "STORAGES", {})
            default_backend = (storages.get("default") or {}).get("BACKEND", "")
            if not default_backend:
                default_backend = getattr(settings, "DEFAULT_FILE_STORAGE", "not set")
            media_url = getattr(settings, "MEDIA_URL", "")
            media_root = getattr(settings, "MEDIA_ROOT", "")
            detail = f"Backend: {default_backend}\nMEDIA_URL: {media_url}\nMEDIA_ROOT: {media_root}"
            return _ok(r, f"Storage: {default_backend.split('.')[-1]}", detail)
        except Exception:
            return _err(r, "Exception reading storage settings.", traceback.format_exc())


def _check_media_write() -> dict:
    r = _check("media_write", "Storage write test")
    with _Timer(r):
        try:
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            test_path = "_diagnostics_probe_.txt"
            default_storage.save(test_path, ContentFile(b"diag-ok"))
            exists = default_storage.exists(test_path)
            default_storage.delete(test_path)
            if exists:
                return _ok(r, "Storage write/read/delete cycle succeeded.")
            return _warn(r, "File was saved but .exists() returned False.")
        except Exception:
            return _err(r, "Storage write test failed.", traceback.format_exc())


def run_storage_diagnostics() -> list[dict]:
    return [
        _check_storage_backend(),
        _check_media_write(),
    ]


# ──────────────────────────────────────────────
# Section 6 – System / Environment
# ──────────────────────────────────────────────

def _check_django_version() -> dict:
    r = _check("django_version", "Django & Python version")
    with _Timer(r):
        try:
            import django
            dv = django.__version__
            pv = sys.version
            return _ok(r, f"Django {dv} on Python {pv.split()[0]}",
                       f"Python: {pv}")
        except Exception:
            return _err(r, "Exception reading versions.", traceback.format_exc())


def _check_debug_mode() -> dict:
    r = _check("debug_mode", "DEBUG mode")
    with _Timer(r):
        try:
            from django.conf import settings
            if settings.DEBUG:
                return _warn(r, "DEBUG=True is set. Disable in production.",
                             "Set DEBUG=False via environment variable.")
            return _ok(r, "DEBUG=False — production-safe.")
        except Exception:
            return _err(r, "Exception reading DEBUG setting.", traceback.format_exc())


def _check_secret_key() -> dict:
    r = _check("secret_key", "SECRET_KEY configured")
    with _Timer(r):
        try:
            from django.conf import settings
            key = getattr(settings, "SECRET_KEY", "")
            if not key:
                return _err(r, "SECRET_KEY is not set!")
            if key.startswith("django-insecure"):
                return _warn(r, "SECRET_KEY uses the default insecure dev key.",
                             "Generate a strong secret key for production.")
            return _ok(r, "SECRET_KEY is set (value hidden).")
        except Exception:
            return _err(r, "Exception reading SECRET_KEY.", traceback.format_exc())


def _check_allowed_hosts() -> dict:
    r = _check("allowed_hosts", "ALLOWED_HOSTS")
    with _Timer(r):
        try:
            from django.conf import settings
            hosts = getattr(settings, "ALLOWED_HOSTS", [])
            if not hosts:
                return _warn(r, "ALLOWED_HOSTS is empty.")
            if "*" in hosts:
                return _warn(r, "ALLOWED_HOSTS contains '*' — dangerous in production.",
                             str(hosts))
            return _ok(r, f"{len(hosts)} host(s) configured.", ", ".join(str(h) for h in hosts))
        except Exception:
            return _err(r, "Exception reading ALLOWED_HOSTS.", traceback.format_exc())


def _check_platform_cname() -> dict:
    r = _check("platform_cname", "PLATFORM_CNAME setting")
    with _Timer(r):
        try:
            from django.conf import settings
            cname = getattr(settings, "PLATFORM_CNAME", "")
            if not cname:
                return _warn(r, "PLATFORM_CNAME is not set. IP-direct requests may misbehave.")
            return _ok(r, f"PLATFORM_CNAME = {cname}")
        except Exception:
            return _err(r, "Exception reading PLATFORM_CNAME.", traceback.format_exc())


def _check_celery() -> dict:
    r = _check("celery", "Celery / Task queue")
    with _Timer(r):
        try:
            from django.conf import settings
            broker = getattr(settings, "CELERY_BROKER_URL", "") or getattr(settings, "BROKER_URL", "")
            if not broker:
                return _warn(r, "CELERY_BROKER_URL not configured. Async tasks unavailable.")
            # Lightweight socket probe on the broker host
            from urllib.parse import urlparse
            parsed = urlparse(broker)
            host = parsed.hostname or "localhost"
            port = parsed.port or 6379
            try:
                sock = socket.create_connection((host, port), timeout=5)
                sock.close()
                return _ok(r, f"Broker reachable at {host}:{port}.", f"URL: {broker}")
            except (socket.timeout, ConnectionRefusedError, OSError) as exc:
                return _err(r, f"Broker at {host}:{port} unreachable: {exc}", broker)
        except Exception:
            return _err(r, "Exception checking Celery broker.", traceback.format_exc())


def run_system_diagnostics() -> list[dict]:
    return [
        _check_django_version(),
        _check_debug_mode(),
        _check_secret_key(),
        _check_allowed_hosts(),
        _check_platform_cname(),
        _check_celery(),
    ]


# ──────────────────────────────────────────────
# Master runner
# ──────────────────────────────────────────────

SECTIONS: dict[str, dict[str, Any]] = {
    "payments": {
        "label": "Payment Gateways",
        "icon": "payments",
        "description": "Paystack & Flutterwave credentials, API reachability, and active gateway status.",
        "runner": run_payment_diagnostics,
    },
    "email": {
        "label": "Email / SMTP",
        "icon": "email",
        "description": "Django email backend, SMTP TCP connectivity, and channel configuration.",
        "runner": run_email_diagnostics,
    },
    "messaging": {
        "label": "Messaging & WhatsApp",
        "icon": "chat",
        "description": "WhatsApp Business, SMS, and notification channel configuration.",
        "runner": run_messaging_diagnostics,
    },
    "database": {
        "label": "Database & Cache",
        "icon": "storage",
        "description": "PostgreSQL connection, tenant count, migration status, and Redis cache.",
        "runner": run_database_diagnostics,
    },
    "storage": {
        "label": "Storage / Media",
        "icon": "folder_open",
        "description": "File storage backend configuration and write capability.",
        "runner": run_storage_diagnostics,
    },
    "system": {
        "label": "System / Environment",
        "icon": "settings",
        "description": "Django version, DEBUG mode, secrets, allowed hosts, and task queue.",
        "runner": run_system_diagnostics,
    },
}


def run_section(section_key: str) -> list[dict]:
    """Run all checks for a named section. Returns empty list for unknown sections."""
    section = SECTIONS.get(section_key)
    if not section:
        return []
    try:
        return section["runner"]()
    except Exception:
        return [{
            "name": "section_error",
            "label": "Section Error",
            "status": "error",
            "message": f"Section '{section_key}' crashed.",
            "detail": traceback.format_exc(),
            "latency_ms": 0,
        }]


def run_all_diagnostics() -> list[dict[str, Any]]:
    """Run all sections. Returns a list of section dicts for template rendering."""
    result = []
    for key, meta in SECTIONS.items():
        checks = run_section(key)
        statuses = [c["status"] for c in checks]
        if "error" in statuses:
            overall = "error"
        elif "warning" in statuses:
            overall = "warning"
        elif all(s == "ok" for s in statuses):
            overall = "ok"
        else:
            overall = "unknown"
        result.append({
            "key": key,
            "label": meta["label"],
            "icon": meta["icon"],
            "description": meta["description"],
            "overall": overall,
            "checks": checks,
        })
    return result
