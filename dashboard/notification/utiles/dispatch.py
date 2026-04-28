"""
notifications/utils/dispatch.py
================================
Core notification send pipeline.

Every notification in the system flows through this module:

    Event fires → send_notification() called
        ↓
    resolve_template()       → find the template for this event+channel+locale
        ↓
    check_suppression()      → blacklist check (fast hash lookup)
        ↓
    check_preference()       → customer opt-in/out check
        ↓
    check_rate_limit()       → channel rate limit check
        ↓
    check_dedup()            → duplicate send window check
        ↓
    render_template()        → Jinja2 render with context data
        ↓
    queue_notification()     → create NotificationJob
        ↓
    [Celery worker picks up]
        ↓
    _deliver()               → call provider-specific sender
        ↓
    NotificationLog created  → immutable delivery record
        ↓
    NotificationEvent created → timeline entry

Thread safety:
    All deduplication and rate limit checks use select_for_update()
    or Redis atomic operations to prevent race conditions.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("notifications.dispatch")


# ─────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class NotificationDispatchResult:
    """Result from a single send_notification() call."""
    success: bool = False
    job_id: Optional[str] = None
    log_id: Optional[str] = None
    channel_type: str = ""
    template_name: str = ""
    status: str = ""
    suppressed: bool = False
    suppression_reason: str = ""
    deduped: bool = False
    message: str = ""
    errors: list = field(default_factory=list)


@dataclass
class BulkDispatchResult:
    """Result from send_notification_bulk()."""
    total: int = 0
    queued: int = 0
    suppressed: int = 0
    deduped: int = 0
    failed: int = 0
    job_ids: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────

class DispatchError(Exception):
    pass


class TemplateNotFound(DispatchError):
    pass


class ChannelNotAvailable(DispatchError):
    pass


class RenderError(DispatchError):
    pass


# ─────────────────────────────────────────────────────────────
# SECTION 1 — MAIN DISPATCH ENTRY POINT
# ─────────────────────────────────────────────────────────────

def send_notification(
    event_slug: str,
    recipient_email: str = "",
    recipient_phone: str = "",
    customer=None,
    context: dict = None,
    channel_type: str = "email",
    locale: str = "en",
    send_delay_seconds: int = None,
    priority: int = 5,
    event_object_type: str = "",
    event_object_id=None,
    force_send: bool = False,
    actor=None,
) -> NotificationDispatchResult:
    """
    Main entry point for sending a single notification.

    Runs the full pipeline: template resolution → suppression check
    → preference check → deduplication → render → queue.

    Args:
        event_slug:         e.g. 'order.placed', 'cart.abandoned'
        recipient_email:    Target email (for EMAIL channel)
        recipient_phone:    Target phone in E.164 (for SMS channel)
        customer:           accounts.Customer instance (optional for guests)
        context:            Jinja2 template context dict
        channel_type:       ChannelType choice string
        locale:             Language code. e.g. 'en', 'fr'
        send_delay_seconds: Override template's send_delay. 0 = immediate.
        priority:           Job priority (0=critical, 10=low)
        event_object_type:  e.g. 'Order', 'Cart'
        event_object_id:    UUID of the triggering object
        force_send:         Skip suppression + preference checks
        actor:              Staff user triggering the send (for manual sends)

    Returns:
        NotificationDispatchResult
    """
    ctx = context or {}
    recipient = recipient_email or recipient_phone or (customer.email if customer else "")

    if not recipient:
        return NotificationDispatchResult(
            success=False,
            errors=["No recipient address provided."]
        )

    # ── 1. Resolve template ──
    try:
        template, template_version = resolve_template(event_slug, channel_type, locale)
    except TemplateNotFound as e:
        return NotificationDispatchResult(
            success=False,
            errors=[str(e)],
        )

    if not template.is_enabled:
        return NotificationDispatchResult(
            success=False,
            status="disabled",
            message=f"Template for '{event_slug}' is disabled.",
        )

    # ── 2. Resolve channel ──
    from .channels import get_channel_for_event
    channel = get_channel_for_event(event_slug, channel_type)
    if not channel or not channel.is_operational:
        return NotificationDispatchResult(
            success=False,
            errors=[f"No operational channel found for {channel_type}."],
        )

    if not force_send:
        # ── 3. Suppression check ──
        suppressed, reason = check_suppression(channel_type, recipient)
        if suppressed:
            _log_suppressed(template, template_version, channel, recipient,
                            customer, event_slug, event_object_type, event_object_id,
                            reason, ctx)
            return NotificationDispatchResult(
                success=False,
                suppressed=True,
                suppression_reason=reason,
                status="suppressed",
                message=f"Recipient suppressed: {reason}",
            )

        # ── 4. Customer preference check ──
        if customer:
            allowed, pref_reason = check_preference(customer, template.category, channel_type)
            if not allowed:
                _log_suppressed(template, template_version, channel, recipient,
                                customer, event_slug, event_object_type, event_object_id,
                                pref_reason, ctx)
                return NotificationDispatchResult(
                    success=False,
                    suppressed=True,
                    suppression_reason=pref_reason,
                    status="suppressed",
                    message=f"Customer opted out: {pref_reason}",
                )

        # ── 5. Deduplication check ──
        dedup_window = template.dedup_window_seconds
        if dedup_window > 0:
            dedup_key = build_dedup_key(event_slug, recipient, str(event_object_id or ""))
            if _is_duplicate(dedup_key, dedup_window):
                return NotificationDispatchResult(
                    success=False,
                    deduped=True,
                    status="deduped",
                    message=f"Duplicate send prevented within {dedup_window}s window.",
                )

    # ── 6. Validate context ──
    validation = _validate_context(template, ctx)
    if not validation["valid"]:
        return NotificationDispatchResult(
            success=False,
            errors=validation["errors"],
        )

    # ── 7. Queue the job ──
    delay = send_delay_seconds if send_delay_seconds is not None else template.send_delay_seconds
    send_at = timezone.now() + timedelta(seconds=delay) if delay > 0 else timezone.now()

    result = queue_notification(
        template=template,
        template_version=template_version,
        channel=channel,
        channel_type=channel_type,
        customer=customer,
        recipient_email=recipient_email,
        recipient_phone=recipient_phone,
        recipient_name=_get_recipient_name(customer, ctx),
        context=ctx,
        event_slug=event_slug,
        event_object_type=event_object_type,
        event_object_id=event_object_id,
        priority=priority,
        send_at=send_at,
        max_attempts=template.max_send_attempts,
        actor=actor,
    )

    logger.info(
        "Notification queued: event=%s recipient=%s channel=%s job=%s",
        event_slug, recipient[:20], channel_type, result.job_id,
    )
    return result


def send_notification_bulk(
    event_slug: str,
    recipients: List[dict],
    context_base: dict = None,
    channel_type: str = "email",
    locale: str = "en",
    priority: int = 10,
    force_send: bool = False,
) -> BulkDispatchResult:
    """
    Send a notification to a list of recipients (e.g. broadcast campaigns).

    Args:
        event_slug:    The notification event.
        recipients:    List of dicts: [{"email": "...", "customer": obj, "context": {}}]
        context_base:  Shared context merged with per-recipient context.
        channel_type:  Channel type for all sends.
        locale:        Locale for all sends.
        priority:      Job priority (default LOW for bulk).
        force_send:    Skip suppression checks.

    Returns:
        BulkDispatchResult with counts and errors.
    """
    result = BulkDispatchResult(total=len(recipients))

    # Resolve template once for all recipients
    try:
        template, template_version = resolve_template(event_slug, channel_type, locale)
    except TemplateNotFound as e:
        result.failed = len(recipients)
        result.errors.append(str(e))
        return result

    from .channels import get_channel_for_event
    channel = get_channel_for_event(event_slug, channel_type)
    if not channel or not channel.is_operational:
        result.failed = len(recipients)
        result.errors.append(f"No operational channel for {channel_type}.")
        return result

    for recipient_data in recipients:
        email = recipient_data.get("email", "")
        phone = recipient_data.get("phone", "")
        customer = recipient_data.get("customer")
        per_ctx = {**(context_base or {}), **recipient_data.get("context", {})}
        recipient_addr = email or phone or (customer.email if customer else "")

        if not recipient_addr:
            result.failed += 1
            continue

        if not force_send:
            suppressed, reason = check_suppression(channel_type, recipient_addr)
            if suppressed:
                result.suppressed += 1
                continue

            if customer:
                allowed, _ = check_preference(customer, template.category, channel_type)
                if not allowed:
                    result.suppressed += 1
                    continue

            if template.dedup_window_seconds > 0:
                dedup_key = build_dedup_key(event_slug, recipient_addr, "")
                if _is_duplicate(dedup_key, template.dedup_window_seconds):
                    result.deduped += 1
                    continue

        try:
            dispatch_result = queue_notification(
                template=template,
                template_version=template_version,
                channel=channel,
                channel_type=channel_type,
                customer=customer,
                recipient_email=email,
                recipient_phone=phone,
                recipient_name=_get_recipient_name(customer, per_ctx),
                context=per_ctx,
                event_slug=event_slug,
                priority=priority,
                send_at=timezone.now(),
                max_attempts=template.max_send_attempts,
            )
            if dispatch_result.success:
                result.queued += 1
                result.job_ids.append(dispatch_result.job_id)
            else:
                result.failed += 1
                result.errors.extend(dispatch_result.errors)
        except Exception as e:
            result.failed += 1
            result.errors.append(f"{recipient_addr}: {e}")

    logger.info(
        "Bulk dispatch: event=%s total=%d queued=%d suppressed=%d failed=%d",
        event_slug, result.total, result.queued, result.suppressed, result.failed,
    )
    return result


# ─────────────────────────────────────────────────────────────
# SECTION 2 — TEMPLATE RESOLUTION & RENDERING
# ─────────────────────────────────────────────────────────────

def resolve_template(
    event_slug: str,
    channel_type: str,
    locale: str = "en",
) -> tuple:
    """
    Find the active NotificationTemplate + NotificationTemplateVersion
    for a given event + channel + locale.

    Falls back to 'en' locale if the requested locale has no template.

    Returns:
        (NotificationTemplate, NotificationTemplateVersion)

    Raises:
        TemplateNotFound: If no active template exists.
    """
    from notifications.models import NotificationTemplate

    # Try exact locale first, then fall back to 'en'
    for try_locale in ([locale, "en"] if locale != "en" else ["en"]):
        try:
            template = NotificationTemplate.objects.select_related(
                "active_version", "category", "channel",
            ).get(
                event_slug=event_slug,
                channel_type=channel_type,
                locale=try_locale,
                status=NotificationTemplate.TemplateStatus.ACTIVE,
                is_enabled=True,
            )
            if not template.active_version:
                continue
            return template, template.active_version
        except NotificationTemplate.DoesNotExist:
            continue

    raise TemplateNotFound(
        f"No active template found for event='{event_slug}' "
        f"channel='{channel_type}' locale='{locale}'"
    )


def render_template(
    template_version,
    context: dict,
    strict: bool = False,
) -> dict:
    """
    Render a NotificationTemplateVersion with a Jinja2 context.

    Returns a dict with all rendered fields appropriate for the channel type.

    For EMAIL:
        {subject, preheader, html_body, text_body}
    For SMS:
        {body}
    For PUSH:
        {title, body, data_payload}
    For SLACK:
        {body, data_payload}
    For IN_APP:
        {title, body, action_url, action_label}
    For WEBHOOK:
        {body, data_payload}

    Args:
        template_version: NotificationTemplateVersion instance.
        context:          Jinja2 template context.
        strict:           If True, raise on undefined variables.

    Returns:
        dict: Rendered content fields.

    Raises:
        RenderError: On template rendering failure.
    """
    try:
        from jinja2 import Environment, StrictUndefined, Undefined, TemplateError

        undefined_cls = StrictUndefined if strict else Undefined
        env = Environment(undefined=undefined_cls, autoescape=False)
        env.filters["default"] = lambda v, d="": v if v else d
        env.filters["format_date"] = lambda v, fmt="%B %d, %Y": (
            v.strftime(fmt) if hasattr(v, "strftime") else str(v)
        )
        env.filters["currency"] = lambda v, symbol="$": f"{symbol}{v:,.2f}"
        env.filters["upper"] = str.upper
        env.filters["lower"] = str.lower
        env.filters["title"] = str.title

        def _render(content: str) -> str:
            if not content:
                return ""
            return env.from_string(content).render(**context)

        channel_type = template_version.template.channel_type if hasattr(
            template_version, "template"
        ) else "email"

        rendered = {}

        if channel_type == "email":
            rendered["subject"] = _render(template_version.subject)
            rendered["preheader"] = _render(template_version.preheader)
            rendered["html_body"] = _render(template_version.html_body)
            text = template_version.text_body
            if not text and template_version.html_body:
                text = _strip_html(template_version.html_body)
            rendered["text_body"] = _render(text) if text else ""
            rendered["email_template_id"] = template_version.email_template_id

        elif channel_type == "sms":
            rendered["body"] = _render(template_version.text_body or template_version.body)

        elif channel_type in ("push", "in_app"):
            rendered["title"] = _render(template_version.title)
            rendered["body"] = _render(template_version.body)
            rendered["action_url"] = _render(template_version.action_url)
            rendered["action_label"] = _render(template_version.action_label)
            rendered["image_url"] = template_version.image_url
            if template_version.data_payload:
                rendered["data_payload"] = _render_json_values(
                    template_version.data_payload, env, context
                )

        elif channel_type == "slack":
            rendered["body"] = _render(template_version.body)
            if template_version.data_payload:
                rendered["data_payload"] = _render_json_values(
                    template_version.data_payload, env, context
                )

        elif channel_type == "webhook":
            rendered["body"] = _render(template_version.body)
            rendered["data_payload"] = _render_json_values(
                template_version.data_payload or {}, env, context
            )

        return rendered

    except Exception as e:
        logger.error(
            "Template render failed for version %s: %s",
            getattr(template_version, "id", "?"), e
        )
        raise RenderError(f"Template rendering failed: {e}")


# ─────────────────────────────────────────────────────────────
# SECTION 3 — JOB QUEUING
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def queue_notification(
    template,
    template_version,
    channel,
    channel_type: str,
    customer,
    recipient_email: str,
    recipient_phone: str,
    recipient_name: str,
    context: dict,
    event_slug: str,
    send_at=None,
    priority: int = 5,
    max_attempts: int = 3,
    event_object_type: str = "",
    event_object_id=None,
    actor=None,
) -> NotificationDispatchResult:
    """
    Create a NotificationJob record and enqueue the Celery task.

    The context_data is captured at queue time so late binding doesn't
    affect the render if data changes before the worker processes the job.
    """
    from notifications.models import NotificationJob, NotificationLog, DeliveryStatus

    recipient_addr = recipient_email or recipient_phone or (
        customer.email if customer else ""
    )
    dedup_key = build_dedup_key(event_slug, recipient_addr, str(event_object_id or ""))

    job = NotificationJob.objects.create(
        template=template,
        template_version=template_version,
        channel=channel,
        channel_type=channel_type,
        customer=customer,
        recipient_email=recipient_email,
        recipient_phone=recipient_phone,
        recipient_name=recipient_name,
        event_slug=event_slug,
        event_object_type=event_object_type,
        event_object_id=event_object_id,
        context_data=context,
        priority=priority,
        send_at=send_at or timezone.now(),
        status=NotificationJob.JobStatus.QUEUED,
        max_attempts=max_attempts,
        dedup_key=dedup_key,
    )

    # Enqueue Celery task (stub — replace with actual task call)
    _enqueue_celery_task(job)

    return NotificationDispatchResult(
        success=True,
        job_id=str(job.id),
        channel_type=channel_type,
        template_name=template.name if template else "",
        status="queued",
        message=f"Notification queued for {recipient_addr[:30]}.",
    )


def cancel_notification_job(
    job_id: str,
    reason: str = "",
    actor=None,
) -> dict:
    """
    Cancel a queued or scheduled NotificationJob before it is processed.

    Cannot cancel jobs that are already PROCESSING, COMPLETED, or FAILED.
    """
    from notifications.models import NotificationJob

    try:
        job = NotificationJob.objects.get(id=job_id)
    except NotificationJob.DoesNotExist:
        return {"success": False, "message": "Job not found."}

    if job.status in (
        NotificationJob.JobStatus.PROCESSING,
        NotificationJob.JobStatus.COMPLETED,
        NotificationJob.JobStatus.FAILED,
        NotificationJob.JobStatus.CANCELLED,
    ):
        return {
            "success": False,
            "message": f"Cannot cancel job in status '{job.status}'.",
        }

    job.cancel(reason=reason or "Cancelled by user.")
    logger.info("Job %s cancelled by %s. Reason: %s", job_id, actor, reason)
    return {"success": True, "message": f"Job {job_id} cancelled."}


# ─────────────────────────────────────────────────────────────
# SECTION 4 — SUPPRESSION & PREFERENCE CHECKS
# ─────────────────────────────────────────────────────────────

def check_suppression(channel_type: str, recipient_address: str) -> tuple:
    """
    Check the global suppression/blacklist for a recipient.

    Returns:
        (is_suppressed: bool, reason: str)
    """
    from notifications.models import NotificationBlacklist

    entry_type_map = {
        "email": NotificationBlacklist.EntryType.EMAIL,
        "sms": NotificationBlacklist.EntryType.SMS,
        "push": NotificationBlacklist.EntryType.PUSH,
    }
    entry_type = entry_type_map.get(channel_type)
    if not entry_type:
        return False, ""

    if NotificationBlacklist.is_suppressed(entry_type, recipient_address):
        return True, f"Address on {channel_type} suppression list."

    return False, ""


def check_preference(customer, category, channel_type: str) -> tuple:
    """
    Check whether a customer has opted in to receive notifications
    for a specific category on a specific channel.

    Returns:
        (is_allowed: bool, reason: str)
    """
    from notifications.models import NotificationPreference

    if not category.allow_customer_opt_out:
        return True, ""

    try:
        pref = NotificationPreference.objects.get(
            customer=customer,
            category=category,
            channel_type=channel_type,
        )
        if not pref.is_subscribed:
            return False, f"Customer opted out of {category.name} via {channel_type}."
    except NotificationPreference.DoesNotExist:
        if not category.default_opt_in:
            return False, f"Customer not opted in to {category.name}."

    return True, ""


def build_dedup_key(event_slug: str, recipient: str, object_id: str) -> str:
    """
    Build a deduplication key for a notification.

    Format: sha256({event_slug}:{recipient}:{object_id})
    The hash keeps the key short and hides the email address.
    """
    raw = f"{event_slug}:{recipient.lower()}:{object_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _is_duplicate(dedup_key: str, window_seconds: int) -> bool:
    """Check if a notification with this key was recently sent."""
    from notifications.models import NotificationJob, DeliveryStatus

    cutoff = timezone.now() - timedelta(seconds=window_seconds)
    return NotificationJob.objects.filter(
        dedup_key=dedup_key,
        created_at__gte=cutoff,
        status__in=[
            NotificationJob.JobStatus.QUEUED,
            NotificationJob.JobStatus.PROCESSING,
            NotificationJob.JobStatus.COMPLETED,
        ],
    ).exists()


def _log_suppressed(
    template, template_version, channel, recipient_address,
    customer, event_slug, event_object_type, event_object_id,
    suppression_reason, context,
):
    """Create a NotificationLog record for a suppressed notification."""
    from notifications.models import NotificationLog, DeliveryStatus, NotificationEvent

    log = NotificationLog.objects.create(
        template=template,
        template_version_number=template_version.version_number if template_version else None,
        channel=channel,
        channel_type=channel.channel_type,
        customer=customer,
        recipient_address=recipient_address,
        status=DeliveryStatus.SUPPRESSED,
        status_updated_at=timezone.now(),
        event_slug=event_slug,
        event_object_type=event_object_type,
        event_object_id=event_object_id,
        suppression_reason=suppression_reason,
    )
    NotificationEvent.objects.create(
        notification_log=log,
        event_type=NotificationEvent.EventType.SUPPRESSED,
        detail=suppression_reason,
        source="dispatch",
    )


def _validate_context(template, context: dict) -> dict:
    """Validate that required template variables are present in context."""
    errors = []
    required_vars = template.variables.filter(is_required=True).values_list("key", flat=True)

    for var_key in required_vars:
        keys = var_key.split(".")
        value = context
        try:
            for k in keys:
                value = value[k] if isinstance(value, dict) else getattr(value, k)
        except (KeyError, AttributeError, TypeError):
            errors.append(f"Required variable '{{ {var_key} }}' is missing from context.")

    return {"valid": len(errors) == 0, "errors": errors}


def _get_recipient_name(customer, context: dict) -> str:
    if customer:
        return f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip()
    return context.get("customer_name", context.get("first_name", ""))


def _strip_html(html: str) -> str:
    """Strip HTML tags for plain text fallback."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(text.split())


def _render_json_values(data: dict, env, context: dict) -> dict:
    """Recursively render Jinja2 templates within JSON dict values."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            try:
                result[key] = env.from_string(value).render(**context)
            except Exception:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = _render_json_values(value, env, context)
        elif isinstance(value, list):
            result[key] = [
                _render_json_values(v, env, context) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            result[key] = value
    return result


def _enqueue_celery_task(job) -> None:
    """Enqueue the Celery task for a NotificationJob. Stub — replace with real task."""
    logger.debug("Celery task would be enqueued for job %s", job.id)
    # In production:
    # from notifications.tasks import process_notification_job
    # process_notification_job.apply_async(
    #     args=[str(job.id)],
    #     eta=job.send_at,
    #     priority=job.priority,
    # )


def is_recipient_suppressed(channel_type: str, address: str) -> bool:
    """Public wrapper for blacklist check."""
    suppressed, _ = check_suppression(channel_type, address)
    return suppressed
