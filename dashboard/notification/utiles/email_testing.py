from __future__ import annotations

import smtplib
import socket
import time
from dataclasses import dataclass
from email.utils import formataddr

from django.core.mail import EmailMultiAlternatives, get_connection

from dashboard.notification.models import EmailChannelConfig


@dataclass
class EmailSmokeTestResult:
    success: bool
    recipient: str = ""
    subject: str = ""
    latency_ms: int = 0
    error_code: str = ""
    diagnostic: str = ""
    provider_response: str = ""


def send_smtp_smoke_test(
    config: EmailChannelConfig,
    recipient_email: str,
    subject: str,
    message: str,
) -> EmailSmokeTestResult:
    recipient = recipient_email.strip()
    if not recipient:
        return EmailSmokeTestResult(
            success=False,
            error_code="missing_recipient",
            diagnostic="A recipient email address is required before running the SMTP test.",
        )

    if config.provider != EmailChannelConfig.EmailProvider.SMTP:
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            error_code="unsupported_provider",
            diagnostic="This test page currently supports SMTP channels only.",
        )

    if not config.from_email:
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            error_code="missing_from_email",
            diagnostic="Add a From Email on the channel before testing SMTP delivery.",
        )

    if not config.smtp_host:
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            error_code="missing_smtp_host",
            diagnostic="SMTP Host is missing on this channel.",
        )

    start = time.monotonic()
    try:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=config.smtp_host,
            port=config.smtp_port or 587,
            username=config.smtp_username or None,
            password=config.smtp_password or None,
            use_tls=config.smtp_encryption == EmailChannelConfig.SMTPEncryption.STARTTLS,
            use_ssl=config.smtp_encryption == EmailChannelConfig.SMTPEncryption.SSL,
            timeout=config.smtp_timeout or 30,
            fail_silently=False,
        )

        from_address = (
            formataddr((config.from_name, config.from_email))
            if config.from_name
            else config.from_email
        )
        reply_to = [config.reply_to] if config.reply_to else None

        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=from_address,
            to=[recipient],
            reply_to=reply_to,
            connection=connection,
        )

        sent_count = connection.send_messages([email])
        latency_ms = int((time.monotonic() - start) * 1000)

        if sent_count != 1:
            return EmailSmokeTestResult(
                success=False,
                recipient=recipient,
                subject=subject,
                latency_ms=latency_ms,
                error_code="send_not_confirmed",
                diagnostic="The SMTP server accepted the connection, but Django did not confirm a sent message.",
            )

        return EmailSmokeTestResult(
            success=True,
            recipient=recipient,
            subject=subject,
            latency_ms=latency_ms,
            diagnostic=f"Test email accepted for delivery to {recipient}.",
        )
    except smtplib.SMTPAuthenticationError as exc:
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code="smtp_auth_failed",
            diagnostic="SMTP authentication failed. Check the username, password or app password configured on this channel.",
            provider_response=_decode_provider_response(exc),
        )
    except smtplib.SMTPConnectError as exc:
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code="smtp_connect_failed",
            diagnostic="The app could not establish an SMTP connection to the configured host and port.",
            provider_response=_decode_provider_response(exc),
        )
    except smtplib.SMTPRecipientsRefused as exc:
        refused = ", ".join(exc.recipients.keys())
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code="recipient_refused",
            diagnostic=f"The SMTP server refused the recipient address: {refused}.",
            provider_response=str(exc.recipients),
        )
    except smtplib.SMTPSenderRefused as exc:
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code="sender_refused",
            diagnostic="The SMTP server refused the configured From Email address.",
            provider_response=_decode_provider_response(exc),
        )
    except smtplib.SMTPServerDisconnected as exc:
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code="server_disconnected",
            diagnostic="The SMTP server disconnected before the test email completed.",
            provider_response=str(exc),
        )
    except (socket.gaierror, TimeoutError, socket.timeout) as exc:
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code="network_error",
            diagnostic="The SMTP host could not be reached. Double-check the host, port, firewall and outbound network access.",
            provider_response=str(exc),
        )
    except Exception as exc:  # pragma: no cover - safety net for unexpected providers
        return EmailSmokeTestResult(
            success=False,
            recipient=recipient,
            subject=subject,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code=exc.__class__.__name__.lower(),
            diagnostic="The SMTP test failed with an unexpected error.",
            provider_response=str(exc),
        )


def _decode_provider_response(exc: Exception) -> str:
    if not getattr(exc, "smtp_error", None):
        return str(exc)

    smtp_error = exc.smtp_error
    if isinstance(smtp_error, bytes):
        try:
            return smtp_error.decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - extremely defensive
            return repr(smtp_error)
    return str(smtp_error)
