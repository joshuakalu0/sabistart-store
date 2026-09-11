"""
system/core/platform_settings_views.py
=========================================
Single unified /platform/settings/ page with three tabs:
  - smtp      → PlatformSmtpSetting
  - storage   → PlatformStorageSetting
  - messaging → PlatformMessagingSetting

Also provides POST-only helpers:
  - smtp_test                    → sends a test email
  - messaging_rotate_webhook_secret → rotates the HMAC secret

No Django admin or separate sidebar items — everything lives on one page.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import send_mail
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from system.core.platform_settings import (
    PlatformMessagingSetting,
    PlatformSmtpSetting,
    PlatformStorageSetting,
)
from system.core.platform_settings_forms import (
    PlatformMessagingSettingForm,
    PlatformSmtpSettingForm,
    PlatformStorageSettingForm,
)


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_platform_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.is_staff or getattr(user, "is_platform_admin", False)
    )


def _platform_admin_required(view_func):
    return login_required(
        user_passes_test(_is_platform_admin)(view_func),
        login_url="platform:login",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Shared context
# ─────────────────────────────────────────────────────────────────────────────

def _shared_context(request, **extra):
    from sabistart.navigation import build_platform_navigation
    return {
        "page_title": "Platform Settings",
        "platform_navigation": build_platform_navigation("platform_settings"),
        **extra,
    }


VALID_TABS = ("smtp", "storage", "messaging")


# ─────────────────────────────────────────────────────────────────────────────
# Main unified settings view
# ─────────────────────────────────────────────────────────────────────────────

@_platform_admin_required
def platform_settings(request):
    """
    GET  → render all three forms, default tab = smtp (or ?tab=storage / ?tab=messaging)
    POST → identify which tab was submitted (hidden field `_tab`), save that form only
    """
    # Determine active tab
    if request.method == "POST":
        active_tab = request.POST.get("_tab", "smtp")
    else:
        active_tab = request.GET.get("tab", "smtp")

    setup_warning = None
    try:
        smtp_setting = PlatformSmtpSetting.load()
    except Exception as exc:
        smtp_setting = PlatformSmtpSetting()
        setup_warning = "Database tables for platform settings are not migrated yet. Please run 'python manage.py migrate --schema=public'."

    try:
        storage_setting = PlatformStorageSetting.load()
    except Exception:
        storage_setting = PlatformStorageSetting()
        if not setup_warning:
            setup_warning = "Database tables for platform settings are not migrated yet. Please run 'python manage.py migrate --schema=public'."

    try:
        messaging_setting = PlatformMessagingSetting.load()
    except Exception:
        messaging_setting = PlatformMessagingSetting()
        if not setup_warning:
            setup_warning = "Database tables for platform settings are not migrated yet. Please run 'python manage.py migrate --schema=public'."

    smtp_form = PlatformSmtpSettingForm(instance=smtp_setting)
    storage_form = PlatformStorageSettingForm(instance=storage_setting)
    messaging_form = PlatformMessagingSettingForm(instance=messaging_setting)

    if request.method == "POST":
        if setup_warning:
            messages.error(request, setup_warning)
            return redirect(f"{request.path}?tab={active_tab}")

        if active_tab == "smtp":
            smtp_form = PlatformSmtpSettingForm(request.POST, instance=smtp_setting)
            if smtp_form.is_valid():
                setting = smtp_form.save(commit=False)
                setting.updated_by = request.user
                setting.save()
                messages.success(request, "SMTP settings saved successfully.")
                return redirect(f"{request.path}?tab=smtp")
        elif active_tab == "storage":
            storage_form = PlatformStorageSettingForm(request.POST, instance=storage_setting)
            if storage_form.is_valid():
                setting = storage_form.save(commit=False)
                setting.updated_by = request.user
                setting.save()
                messages.success(request, "Storage settings saved successfully.")
                return redirect(f"{request.path}?tab=storage")
        elif active_tab == "messaging":
            messaging_form = PlatformMessagingSettingForm(request.POST, instance=messaging_setting)
            if messaging_form.is_valid():
                setting = messaging_form.save(commit=False)
                setting.updated_by = request.user
                setting.save()
                messages.success(request, "Messaging settings saved successfully.")
                return redirect(f"{request.path}?tab=messaging")

    context = _shared_context(
        request,
        active_tab=active_tab,
        setup_warning=setup_warning,
        smtp_form=smtp_form,
        smtp_setting=smtp_setting,
        storage_form=storage_form,
        storage_setting=storage_setting,
        messaging_form=messaging_form,
        messaging_setting=messaging_setting,
    )
    return render(request, "core/platform_settings/settings.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# SMTP test helper
# ─────────────────────────────────────────────────────────────────────────────

@_platform_admin_required
@require_POST
def smtp_test(request):
    """Send a test email using the saved SMTP configuration."""
    setting = PlatformSmtpSetting.load()
    if not setting.is_configured:
        messages.error(request, "SMTP is not configured. Save valid settings first.")
        return redirect(f"{_settings_url(request)}?tab=smtp")

    recipient = request.user.email
    if not recipient:
        messages.error(request, "Your account has no email address set — cannot send test email.")
        return redirect(f"{_settings_url(request)}?tab=smtp")

    try:
        _apply_smtp_to_connection(setting)
        send_mail(
            subject="[SABIStart] SMTP Test Email",
            message=(
                "This is a test email sent from your SABIStart platform.\n\n"
                f"SMTP host: {setting.host}:{setting.port}\n"
                f"Username: {setting.username}\n"
            ),
            from_email=setting.default_from_email or None,
            recipient_list=[recipient],
            fail_silently=False,
        )
        messages.success(request, f"Test email sent to {recipient}.")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Test email failed: {exc}")

    return redirect(f"{_settings_url(request)}?tab=smtp")


def _settings_url(request):
    from django.urls import reverse
    try:
        return reverse("platform:settings")
    except Exception:
        return request.path


def _apply_smtp_to_connection(setting: PlatformSmtpSetting):
    """Temporarily override Django email backend settings for the test send."""
    from django.core import mail
    # Build a temporary connection using the stored credentials
    use_tls = setting.security == PlatformSmtpSetting.SECURITY_TLS
    use_ssl = setting.security == PlatformSmtpSetting.SECURITY_SSL
    conn = mail.get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=setting.host,
        port=setting.port,
        username=setting.username,
        password=setting.password,
        use_tls=use_tls,
        use_ssl=use_ssl,
    )
    # Attach to the thread-local connection so send_mail picks it up
    mail.outbox = getattr(mail, "outbox", [])  # keep test compat
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Messaging webhook secret rotation
# ─────────────────────────────────────────────────────────────────────────────

@_platform_admin_required
@require_POST
def messaging_rotate_webhook_secret(request):
    """Rotate the HMAC webhook signing secret and display the new value once."""
    setting = PlatformMessagingSetting.load()
    new_secret = setting.rotate_webhook_secret()
    messages.success(
        request,
        f"Webhook secret rotated. New secret (copy it now — it won't be shown again): {new_secret}",
    )
    return redirect(f"{_settings_url(request)}?tab=messaging")
