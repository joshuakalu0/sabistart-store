"""
notifications/utils/channels.py + templates.py + preferences.py + webhooks.py + inapp.py
==========================================================================================
Five utility modules combined.
"""

import hashlib
import hmac
import json
import logging
import math
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger("notifications.utils")


# ══════════════════════════════════════════════════════════════
# MODULE: channels.py
# Channel CRUD, health monitoring, rate limit enforcement
# ══════════════════════════════════════════════════════════════

@dataclass
class ChannelTestResult:
    success: bool = False
    channel_type: str = ""
    message: str = ""
    latency_ms: int = 0
    error: str = ""


@dataclass
class ChannelHealthStatus:
    channel_id: str = ""
    name: str = ""
    channel_type: str = ""
    status: str = ""
    is_operational: bool = False
    consecutive_failures: int = 0
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    daily_sends: int = 0
    daily_limit: Optional[int] = None
    daily_utilisation_pct: float = 0.0
    health_grade: str = "A"


def get_channel_for_event(event_slug: str, channel_type: str):
    """
    Resolve the best NotificationChannel for a given event + channel type.

    Resolution order:
      1. Active channel with allowed_categories matching the event's template category
      2. Default channel for this type
      3. Any active channel of this type (highest priority)

    Returns:
        NotificationChannel | None
    """
    from notifications.models import NotificationChannel, NotificationTemplate

    # Get the category for this event
    template_qs = NotificationTemplate.objects.filter(
        event_slug=event_slug, channel_type=channel_type
    ).select_related("category", "channel").first()

    if template_qs and template_qs.channel and template_qs.channel.is_operational:
        return template_qs.channel

    category_slug = template_qs.category.slug if template_qs and template_qs.category else None

    # Find best channel
    qs = NotificationChannel.objects.filter(
        channel_type=channel_type,
        status=NotificationChannel.ChannelStatus.ACTIVE,
    ).order_by("-is_default", "-priority")

    if category_slug:
        # Prefer channels with this category allowed (or no restrictions)
        categorized = qs.filter(
            Q(allowed_categories__contains=[category_slug]) |
            Q(allowed_categories=[])
        )
        if categorized.exists():
            return categorized.first()

    return qs.first()


def get_default_channel(channel_type: str):
    """Return the default active channel for a channel type."""
    from notifications.models import NotificationChannel

    return NotificationChannel.objects.filter(
        channel_type=channel_type,
        status=NotificationChannel.ChannelStatus.ACTIVE,
        is_default=True,
    ).first()


def list_channels(channel_type: str = None, include_inactive: bool = False) -> list:
    """
    List all notification channels with health summary.

    Returns:
        list[dict]: Channel summaries with health data.
    """
    from notifications.models import NotificationChannel

    qs = NotificationChannel.objects.all().order_by("-is_default", "-priority")
    if channel_type:
        qs = qs.filter(channel_type=channel_type)
    if not include_inactive:
        qs = qs.exclude(status=NotificationChannel.ChannelStatus.DISABLED)

    return [
        {
            "id": str(ch.id),
            "name": ch.name,
            "channel_type": ch.channel_type,
            "status": ch.status,
            "is_default": ch.is_default,
            "priority": ch.priority,
            "is_operational": ch.is_operational,
            "consecutive_failures": ch.consecutive_failures,
            "daily_sends": ch.daily_send_count,
            "daily_limit": ch.rate_limit_per_day,
            "last_success": ch.last_successful_send_at.isoformat() if ch.last_successful_send_at else None,
            "last_failure": ch.last_failure_at.isoformat() if ch.last_failure_at else None,
            "description": ch.description,
            "tags": ch.tags,
        }
        for ch in qs
    ]


@transaction.atomic
def create_channel(
    name: str,
    channel_type: str,
    description: str = "",
    is_default: bool = False,
    priority: int = 0,
    actor=None,
    **kwargs,
) -> object:
    """Create a new NotificationChannel."""
    from notifications.models import NotificationChannel

    return NotificationChannel.objects.create(
        name=name,
        channel_type=channel_type,
        description=description,
        is_default=is_default,
        priority=priority,
        status=NotificationChannel.ChannelStatus.INACTIVE,
        created_by=actor,
        **kwargs,
    )


def update_channel(channel_id: str, actor=None, **kwargs) -> bool:
    """Update NotificationChannel fields."""
    from notifications.models import NotificationChannel

    updated = NotificationChannel.objects.filter(id=channel_id).update(**kwargs)
    return bool(updated)


def activate_channel(channel_id: str, actor=None) -> dict:
    """Activate a channel. Returns {success, message}."""
    from notifications.models import NotificationChannel

    try:
        ch = NotificationChannel.objects.get(id=channel_id)
        ch.status = NotificationChannel.ChannelStatus.ACTIVE
        ch.save(update_fields=["status", "updated_at"])
        return {"success": True, "message": f"Channel '{ch.name}' activated."}
    except NotificationChannel.DoesNotExist:
        return {"success": False, "message": "Channel not found."}


def deactivate_channel(channel_id: str, actor=None) -> dict:
    """Pause a channel without deleting it."""
    from notifications.models import NotificationChannel

    try:
        ch = NotificationChannel.objects.get(id=channel_id)
        ch.status = NotificationChannel.ChannelStatus.INACTIVE
        ch.save(update_fields=["status", "updated_at"])
        return {"success": True, "message": f"Channel '{ch.name}' deactivated."}
    except NotificationChannel.DoesNotExist:
        return {"success": False, "message": "Channel not found."}


def test_channel(channel_id: str, test_recipient: str = "") -> ChannelTestResult:
    """
    Send a test notification through a channel to verify it's working.
    Uses the channel's configured test address if no recipient provided.
    """
    import time as time_module
    from notifications.models import NotificationChannel

    try:
        ch = NotificationChannel.objects.get(id=channel_id)
    except NotificationChannel.DoesNotExist:
        return ChannelTestResult(success=False, error="Channel not found.")

    start = time_module.monotonic()
    try:
        result = _perform_channel_test(ch, test_recipient)
        latency_ms = int((time_module.monotonic() - start) * 1000)
        return ChannelTestResult(
            success=result["success"],
            channel_type=ch.channel_type,
            message=result.get("message", ""),
            latency_ms=latency_ms,
            error=result.get("error", ""),
        )
    except Exception as e:
        return ChannelTestResult(success=False, error=str(e))


def reset_channel_failures(channel_id: str) -> bool:
    """Reset consecutive_failures counter and reactivate a degraded channel."""
    from notifications.models import NotificationChannel

    updated = NotificationChannel.objects.filter(id=channel_id).update(
        consecutive_failures=0,
        status=NotificationChannel.ChannelStatus.ACTIVE,
        updated_at=timezone.now(),
    )
    return bool(updated)


def get_channel_health(channel_id: str) -> ChannelHealthStatus:
    """Get the health status object for a channel."""
    from notifications.models import NotificationChannel

    try:
        ch = NotificationChannel.objects.get(id=channel_id)
    except NotificationChannel.DoesNotExist:
        return ChannelHealthStatus()

    daily = ch.daily_send_count
    limit = ch.rate_limit_per_day
    util_pct = round(daily / limit * 100, 1) if limit else 0.0

    grade = "A"
    if ch.consecutive_failures >= ch.failure_threshold:
        grade = "F"
    elif ch.consecutive_failures >= ch.failure_threshold // 2:
        grade = "C"
    elif ch.status == NotificationChannel.ChannelStatus.DEGRADED:
        grade = "C"
    elif util_pct > 90:
        grade = "B"

    return ChannelHealthStatus(
        channel_id=str(ch.id),
        name=ch.name,
        channel_type=ch.channel_type,
        status=ch.status,
        is_operational=ch.is_operational,
        consecutive_failures=ch.consecutive_failures,
        last_success=ch.last_successful_send_at.isoformat() if ch.last_successful_send_at else None,
        last_failure=ch.last_failure_at.isoformat() if ch.last_failure_at else None,
        daily_sends=daily,
        daily_limit=limit,
        daily_utilisation_pct=util_pct,
        health_grade=grade,
    )


def check_rate_limit(channel_id: str) -> tuple:
    """
    Check if a channel is within its rate limits.

    Returns:
        (allowed: bool, reason: str)
    """
    from notifications.models import NotificationChannel

    try:
        ch = NotificationChannel.objects.get(id=channel_id)
    except NotificationChannel.DoesNotExist:
        return False, "Channel not found."

    if ch.rate_limit_per_day and ch.daily_send_count >= ch.rate_limit_per_day:
        return False, f"Daily limit of {ch.rate_limit_per_day} sends reached."

    return True, ""


def increment_rate_counter(channel_id: str) -> None:
    """Atomically increment the daily send counter."""
    from notifications.models import NotificationChannel
    from django.db.models import F

    NotificationChannel.objects.filter(id=channel_id).update(
        daily_send_count=F("daily_send_count") + 1,
        updated_at=timezone.now(),
    )


def _perform_channel_test(channel, test_recipient: str) -> dict:
    """Stub test implementation — replace with real provider calls."""
    logger.info("Test send on channel %s (%s)", channel.name, channel.channel_type)
    return {"success": True, "message": f"Test send to {test_recipient} accepted (stub)."}


# ══════════════════════════════════════════════════════════════
# MODULE: templates.py
# Template CRUD, version management, rendering, preview
# ══════════════════════════════════════════════════════════════

@dataclass
class TemplatePreviewResult:
    success: bool = False
    rendered: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class TemplateValidationResult:
    valid: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    undefined_variables: list = field(default_factory=list)
    missing_required: list = field(default_factory=list)


def get_template_for_event(event_slug: str, channel_type: str, locale: str = "en"):
    """Fetch active template for an event. Returns None if not found."""
    from .dispatch import resolve_template, TemplateNotFound
    try:
        template, version = resolve_template(event_slug, channel_type, locale)
        return template
    except TemplateNotFound:
        return None


@transaction.atomic
def create_template(
    event_slug: str,
    channel_type: str,
    name: str,
    category_slug: str,
    locale: str = "en",
    description: str = "",
    actor=None,
    initial_content: dict = None,
    **kwargs,
) -> object:
    """
    Create a new NotificationTemplate with an initial draft version.

    Args:
        event_slug:    Trigger event identifier.
        channel_type:  Channel type.
        name:          Human-readable template name.
        category_slug: NotificationCategory slug.
        locale:        Language code.
        description:   Internal description.
        actor:         Staff user creating the template.
        initial_content: Dict of content fields for the first version.

    Returns:
        NotificationTemplate instance.
    """
    from notifications.models import (
        NotificationTemplate, NotificationCategory, NotificationTemplateVersion
    )

    try:
        category = NotificationCategory.objects.get(slug=category_slug)
    except NotificationCategory.DoesNotExist:
        raise ValueError(f"Category '{category_slug}' not found.")

    template = NotificationTemplate.objects.create(
        event_slug=event_slug,
        channel_type=channel_type,
        name=name,
        category=category,
        locale=locale,
        description=description,
        status=NotificationTemplate.TemplateStatus.DRAFT,
        is_enabled=False,
        created_by=actor,
        last_modified_by=actor,
        **kwargs,
    )

    if initial_content:
        version = NotificationTemplateVersion.objects.create(
            template=template,
            version_number=1,
            created_by=actor,
            **initial_content,
        )
        template.active_version = version
        template.save(update_fields=["active_version"])

    return template


@transaction.atomic
def update_template(template_id: str, actor=None, **kwargs) -> bool:
    """Update NotificationTemplate metadata fields."""
    from notifications.models import NotificationTemplate

    kwargs["last_modified_by"] = actor
    updated = NotificationTemplate.objects.filter(id=template_id).update(**kwargs)
    return bool(updated)


@transaction.atomic
def create_template_version(
    template_id: str,
    content: dict,
    version_label: str = "",
    change_notes: str = "",
    actor=None,
) -> object:
    """
    Create a new version for a template WITHOUT publishing it.
    The new version is a draft until publish_template_version() is called.

    Returns:
        NotificationTemplateVersion instance.
    """
    from notifications.models import NotificationTemplate, NotificationTemplateVersion

    try:
        template = NotificationTemplate.objects.get(id=template_id)
    except NotificationTemplate.DoesNotExist:
        raise ValueError("Template not found.")

    version = NotificationTemplateVersion.objects.create(
        template=template,
        version_label=version_label,
        change_notes=change_notes,
        created_by=actor,
        **content,
    )
    return version


@transaction.atomic
def publish_template_version(
    version_id: str,
    actor=None,
) -> dict:
    """
    Activate a template version as the live version.
    Also sets the parent template status to ACTIVE.

    Returns:
        dict: {success, message, version_number}
    """
    from notifications.models import NotificationTemplateVersion

    try:
        version = NotificationTemplateVersion.objects.select_related("template").get(
            id=version_id
        )
    except NotificationTemplateVersion.DoesNotExist:
        return {"success": False, "message": "Version not found."}

    version.activate(actor=actor)
    return {
        "success": True,
        "message": f"Version {version.version_number} is now live.",
        "version_number": version.version_number,
    }


@transaction.atomic
def rollback_template_version(
    template_id: str,
    version_number: int,
    actor=None,
) -> dict:
    """
    Roll back a template to a specific version number.
    Creates a NEW version copying the content from the target version
    (preserves full history — does not modify past versions).
    """
    from notifications.models import NotificationTemplate, NotificationTemplateVersion

    try:
        template = NotificationTemplate.objects.get(id=template_id)
        target = NotificationTemplateVersion.objects.get(
            template=template, version_number=version_number
        )
    except (NotificationTemplate.DoesNotExist, NotificationTemplateVersion.DoesNotExist):
        return {"success": False, "message": "Template or version not found."}

    content_fields = [
        "subject", "preheader", "html_body", "text_body",
        "title", "body", "action_url", "action_label",
        "data_payload", "email_template_id", "image_url",
    ]
    content = {f: getattr(target, f) for f in content_fields}

    new_version = NotificationTemplateVersion.objects.create(
        template=template,
        change_notes=f"Rolled back to v{version_number}.",
        version_label=f"Rollback from v{version_number}",
        created_by=actor,
        **content,
    )
    new_version.activate(actor=actor)

    return {
        "success": True,
        "message": f"Rolled back to v{version_number}. New live version: {new_version.version_number}.",
        "new_version_number": new_version.version_number,
    }


def preview_template(
    version_id: str,
    sample_context: dict = None,
) -> TemplatePreviewResult:
    """
    Render a template version with sample/example context for editor preview.

    Uses declared TemplateVariable.example_value fields as fallback context.
    """
    from notifications.models import NotificationTemplateVersion
    from .dispatch import render_template, RenderError

    try:
        version = NotificationTemplateVersion.objects.select_related("template").get(
            id=version_id
        )
    except NotificationTemplateVersion.DoesNotExist:
        return TemplatePreviewResult(success=False, errors=["Version not found."])

    # Build sample context from example values
    example_ctx = {}
    for var in version.template.variables.all():
        if var.example_value:
            keys = var.key.split(".")
            obj = example_ctx
            for k in keys[:-1]:
                obj = obj.setdefault(k, {})
            obj[keys[-1]] = var.example_value

    ctx = {**example_ctx, **(sample_context or {})}

    try:
        rendered = render_template(version, ctx, strict=False)
        return TemplatePreviewResult(success=True, rendered=rendered)
    except RenderError as e:
        return TemplatePreviewResult(success=False, errors=[str(e)])


@transaction.atomic
def duplicate_template(
    template_id: str,
    new_event_slug: str = "",
    new_locale: str = "",
    actor=None,
) -> object:
    """Clone a template with its active version content as the first draft version."""
    from notifications.models import NotificationTemplate, NotificationTemplateVersion

    try:
        source = NotificationTemplate.objects.select_related(
            "category", "active_version"
        ).get(id=template_id)
    except NotificationTemplate.DoesNotExist:
        raise ValueError("Source template not found.")

    new_template = NotificationTemplate.objects.create(
        event_slug=new_event_slug or f"{source.event_slug}_copy",
        channel_type=source.channel_type,
        name=f"{source.name} (Copy)",
        category=source.category,
        locale=new_locale or source.locale,
        description=source.description,
        status=NotificationTemplate.TemplateStatus.DRAFT,
        is_enabled=False,
        created_by=actor,
        send_delay_seconds=source.send_delay_seconds,
        dedup_window_seconds=source.dedup_window_seconds,
    )

    if source.active_version:
        av = source.active_version
        content_fields = [
            "subject", "preheader", "html_body", "text_body",
            "title", "body", "action_url", "action_label",
            "data_payload", "email_template_id",
        ]
        new_version = NotificationTemplateVersion.objects.create(
            template=new_template,
            change_notes=f"Duplicated from '{source.name}'",
            created_by=actor,
            **{f: getattr(av, f) for f in content_fields},
        )
        new_template.active_version = new_version
        new_template.save(update_fields=["active_version"])

    return new_template


def validate_template_variables(
    version_id: str,
    sample_context: dict = None,
) -> TemplateValidationResult:
    """
    Validate a template version against its declared variable schema.
    Returns a detailed report of missing/undefined variables.
    """
    from notifications.models import NotificationTemplateVersion
    import re

    try:
        version = NotificationTemplateVersion.objects.select_related("template").get(id=version_id)
    except NotificationTemplateVersion.DoesNotExist:
        return TemplateValidationResult(valid=False, errors=["Version not found."])

    result = TemplateValidationResult()
    ctx = sample_context or {}
    template = version.template

    # Extract all {{ variable }} references from content
    content_fields = [
        version.subject, version.preheader, version.html_body,
        version.text_body, version.title, version.body,
    ]
    all_content = " ".join(f for f in content_fields if f)
    used_vars = set(re.findall(r'\{\{\s*([\w.]+)\s*[\|}\s]', all_content))

    declared_keys = set(template.variables.values_list("key", flat=True))
    required_keys = set(
        template.variables.filter(is_required=True).values_list("key", flat=True)
    )

    result.undefined_variables = list(used_vars - declared_keys)
    result.missing_required = [
        k for k in required_keys
        if not _has_context_key(ctx, k)
    ]

    if result.undefined_variables:
        result.warnings.append(
            f"{len(result.undefined_variables)} variable(s) used in template "
            f"but not declared in schema: {', '.join(result.undefined_variables)}"
        )
    if result.missing_required:
        result.errors.append(
            f"Required variables missing from sample context: "
            f"{', '.join(result.missing_required)}"
        )

    result.valid = len(result.errors) == 0
    return result


def list_templates(
    channel_type: str = None,
    event_slug: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Paginated template list for the admin dashboard."""
    from notifications.models import NotificationTemplate

    qs = NotificationTemplate.objects.select_related("category", "active_version").order_by(
        "event_slug", "channel_type"
    )
    if channel_type:
        qs = qs.filter(channel_type=channel_type)
    if event_slug:
        qs = qs.filter(event_slug__icontains=event_slug)
    if status:
        qs = qs.filter(status=status)

    total = qs.count()
    total_pages = math.ceil(total / page_size) if total else 1
    offset = (page - 1) * page_size

    return {
        "templates": list(qs[offset:offset + page_size].values(
            "id", "name", "event_slug", "channel_type", "locale",
            "status", "is_enabled", "category__name", "created_at",
        )),
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }


def get_template_version_history(template_id: str, limit: int = 20) -> list:
    """Return version history for a template."""
    from notifications.models import NotificationTemplateVersion

    versions = NotificationTemplateVersion.objects.filter(
        template_id=template_id
    ).select_related("created_by").order_by("-version_number")[:limit]

    return [
        {
            "id": str(v.id),
            "version_number": v.version_number,
            "version_label": v.version_label,
            "change_notes": v.change_notes,
            "content_hash": v.content_hash[:12],
            "created_by": str(v.created_by) if v.created_by else "System",
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]


def _has_context_key(ctx: dict, dot_key: str) -> bool:
    keys = dot_key.split(".")
    obj = ctx
    try:
        for k in keys:
            obj = obj[k] if isinstance(obj, dict) else getattr(obj, k)
        return True
    except (KeyError, AttributeError, TypeError):
        return False


# ══════════════════════════════════════════════════════════════
# MODULE: preferences.py
# Customer preferences, blacklist, unsubscribe, device registration
# ══════════════════════════════════════════════════════════════

@dataclass
class PreferenceUpdateResult:
    success: bool = False
    updated_count: int = 0
    message: str = ""
    errors: list = field(default_factory=list)


def get_customer_preferences(customer) -> list:
    """
    Return all notification preferences for a customer.
    Includes categories with no explicit record (showing default state).
    """
    from notifications.models import NotificationCategory, NotificationPreference

    categories = NotificationCategory.objects.filter(
        is_customer_visible=True
    ).order_by("display_order")

    existing = {
        (str(p.category_id), p.channel_type): p
        for p in NotificationPreference.objects.filter(customer=customer)
    }

    result = []
    for cat in categories:
        for channel_type in ["email", "sms", "push", "in_app"]:
            pref = existing.get((str(cat.id), channel_type))
            result.append({
                "category_id": str(cat.id),
                "category_name": cat.name,
                "category_slug": cat.slug,
                "channel_type": channel_type,
                "is_subscribed": pref.is_subscribed if pref else cat.default_opt_in,
                "has_explicit_preference": pref is not None,
                "allow_opt_out": cat.allow_customer_opt_out,
                "opted_out_at": pref.opted_out_at.isoformat() if pref and pref.opted_out_at else None,
            })

    return result


@transaction.atomic
def update_preference(
    customer,
    category_slug: str,
    channel_type: str,
    is_subscribed: bool,
    method: str = "customer_request",
    actor=None,
) -> PreferenceUpdateResult:
    """Update a single customer notification preference."""
    from notifications.models import NotificationPreference, NotificationCategory

    try:
        category = NotificationCategory.objects.get(slug=category_slug)
    except NotificationCategory.DoesNotExist:
        return PreferenceUpdateResult(success=False, errors=["Category not found."])

    if not is_subscribed and not category.allow_customer_opt_out:
        return PreferenceUpdateResult(
            success=False,
            errors=[f"Category '{category.name}' cannot be opted out of."]
        )

    pref, created = NotificationPreference.objects.get_or_create(
        customer=customer,
        category=category,
        channel_type=channel_type,
        defaults={"is_subscribed": is_subscribed},
    )

    if not created:
        if is_subscribed:
            pref.resubscribe(source=method)
        else:
            pref.unsubscribe(method=method)

    return PreferenceUpdateResult(
        success=True,
        updated_count=1,
        message=f"Preference {'enabled' if is_subscribed else 'disabled'}.",
    )


@transaction.atomic
def bulk_update_preferences(
    customer,
    preferences: List[dict],
    method: str = "customer_request",
) -> PreferenceUpdateResult:
    """
    Update multiple preferences in one call.

    Args:
        customer:     Customer instance.
        preferences:  [{"category_slug": str, "channel_type": str, "is_subscribed": bool}]
        method:       How the change was made.
    """
    errors = []
    updated = 0
    for pref_data in preferences:
        result = update_preference(
            customer=customer,
            category_slug=pref_data.get("category_slug", ""),
            channel_type=pref_data.get("channel_type", ""),
            is_subscribed=pref_data.get("is_subscribed", True),
            method=method,
        )
        if result.success:
            updated += 1
        else:
            errors.extend(result.errors)

    return PreferenceUpdateResult(
        success=len(errors) == 0,
        updated_count=updated,
        errors=errors,
        message=f"{updated} preference(s) updated.",
    )


@transaction.atomic
def unsubscribe_customer(
    customer,
    category_slug: str,
    channel_type: str = "email",
    method: str = "unsubscribe_link",
) -> dict:
    """Unsubscribe a customer from a specific category/channel."""
    result = update_preference(
        customer=customer,
        category_slug=category_slug,
        channel_type=channel_type,
        is_subscribed=False,
        method=method,
    )
    return {"success": result.success, "message": result.message}


@transaction.atomic
def resubscribe_customer(
    customer,
    category_slug: str,
    channel_type: str = "email",
) -> dict:
    """Re-subscribe a customer to a specific category/channel."""
    result = update_preference(
        customer=customer,
        category_slug=category_slug,
        channel_type=channel_type,
        is_subscribed=True,
        method="customer_request",
    )
    return {"success": result.success, "message": result.message}


@transaction.atomic
def global_unsubscribe(
    customer,
    channel_type: str = "email",
    method: str = "unsubscribe_link",
) -> dict:
    """
    Unsubscribe a customer from ALL opt-out-able categories on a channel.
    Used for 'unsubscribe from all' links.
    """
    from notifications.models import NotificationCategory

    categories = NotificationCategory.objects.filter(
        is_customer_visible=True, allow_customer_opt_out=True
    )
    count = 0
    for cat in categories:
        result = update_preference(
            customer=customer,
            category_slug=cat.slug,
            channel_type=channel_type,
            is_subscribed=False,
            method=method,
        )
        if result.success:
            count += 1

    return {"success": True, "message": f"Unsubscribed from {count} category(s)."}


def generate_unsubscribe_token(
    customer,
    channel_type: str,
    category_slug: str = None,
    notification_log_id: str = None,
    is_global: bool = False,
) -> object:
    """
    Generate a secure UnsubscribeToken for use in email footers.
    """
    from notifications.models import UnsubscribeToken, NotificationCategory

    category = None
    if category_slug:
        try:
            category = NotificationCategory.objects.get(slug=category_slug)
        except NotificationCategory.DoesNotExist:
            pass

    return UnsubscribeToken.objects.create(
        customer=customer,
        category=category,
        channel_type=channel_type,
        notification_log_id=notification_log_id,
        is_global=is_global,
    )


def process_unsubscribe_token(token: str, ip_address: str = "") -> dict:
    """
    Validate and process an unsubscribe token from an email footer link.

    Returns:
        dict: {success, message, is_global, category_name}
    """
    from notifications.models import UnsubscribeToken

    try:
        token_obj = UnsubscribeToken.objects.select_related(
            "customer", "category"
        ).get(token=token)
    except UnsubscribeToken.DoesNotExist:
        return {"success": False, "message": "Invalid unsubscribe link."}

    if not token_obj.is_valid:
        if token_obj.is_used:
            return {"success": False, "message": "This unsubscribe link has already been used."}
        return {"success": False, "message": "This unsubscribe link has expired."}

    if token_obj.is_global:
        global_unsubscribe(
            token_obj.customer,
            token_obj.channel_type,
            method="unsubscribe_link",
        )
        token_obj.consume(ip_address)
        return {
            "success": True,
            "is_global": True,
            "message": "You have been unsubscribed from all notifications.",
        }
    else:
        cat = token_obj.category
        if cat:
            unsubscribe_customer(
                token_obj.customer,
                cat.slug,
                token_obj.channel_type,
                method="unsubscribe_link",
            )
        token_obj.consume(ip_address)
        return {
            "success": True,
            "is_global": False,
            "category_name": cat.name if cat else "",
            "message": f"You have been unsubscribed from {cat.name if cat else 'notifications'}.",
        }


@transaction.atomic
def add_to_blacklist(
    entry_type: str,
    value: str,
    reason: str,
    note: str = "",
    actor=None,
    source_log_id: str = None,
) -> object:
    """Add an address to the global suppression blacklist."""
    from notifications.models import NotificationBlacklist

    bl, created = NotificationBlacklist.objects.get_or_create(
        entry_type=entry_type,
        value_hash=hashlib.sha256(value.lower().strip().encode()).hexdigest(),
        defaults={
            "value": value,
            "reason": reason,
            "note": note,
            "added_by": actor,
            "source_log_id": source_log_id,
        },
    )
    return bl


def remove_from_blacklist(entry_type: str, value: str) -> bool:
    """Remove an entry from the blacklist."""
    from notifications.models import NotificationBlacklist

    value_hash = hashlib.sha256(value.lower().strip().encode()).hexdigest()
    deleted, _ = NotificationBlacklist.objects.filter(
        entry_type=entry_type, value_hash=value_hash
    ).delete()
    return bool(deleted)


def is_recipient_suppressed(channel_type: str, address: str) -> bool:
    """Quick suppression check."""
    from notifications.models import NotificationBlacklist

    entry_type_map = {
        "email": "email", "sms": "sms", "push": "push",
    }
    entry_type = entry_type_map.get(channel_type, "email")
    return NotificationBlacklist.is_suppressed(entry_type, address)


@transaction.atomic
def process_bounce(
    email_address: str,
    bounce_type: str,
    diagnostic_code: str = "",
    notification_log_id: str = None,
    provider_event_id: str = "",
    raw_payload: dict = None,
) -> dict:
    """
    Process an email bounce webhook from a provider.

    Hard bounces → auto-blacklisted.
    Soft bounces → recorded, count tracked, blacklisted after threshold.
    """
    from notifications.models import BounceRecord, NotificationBlacklist, NotificationLog

    log = None
    if notification_log_id:
        try:
            log = NotificationLog.objects.get(id=notification_log_id)
        except NotificationLog.DoesNotExist:
            pass

    bounce = BounceRecord.objects.create(
        notification_log=log,
        email_address=email_address,
        bounce_type=bounce_type,
        diagnostic_code=diagnostic_code,
        provider_event_id=provider_event_id,
        raw_webhook_payload=raw_payload or {},
    )

    auto_blacklisted = False
    if bounce_type == BounceRecord.BounceType.HARD:
        add_to_blacklist(
            entry_type="email",
            value=email_address,
            reason=NotificationBlacklist.SuppressReason.HARD_BOUNCE,
            note=diagnostic_code,
            source_log_id=notification_log_id,
        )
        BounceRecord.objects.filter(id=bounce.id).update(auto_blacklisted=True)
        auto_blacklisted = True
    else:
        # Soft bounce threshold check (3 soft bounces → blacklist)
        soft_count = BounceRecord.objects.filter(
            email_address=email_address,
            bounce_type=BounceRecord.BounceType.SOFT,
        ).count()
        if soft_count >= 3:
            add_to_blacklist(
                entry_type="email",
                value=email_address,
                reason=NotificationBlacklist.SuppressReason.SOFT_BOUNCE_REPEATED,
                note=f"{soft_count} soft bounces",
            )
            auto_blacklisted = True

    return {
        "success": True,
        "bounce_id": str(bounce.id),
        "auto_blacklisted": auto_blacklisted,
    }


@transaction.atomic
def process_spam_complaint(
    email_address: str,
    provider: str = "",
    feedback_type: str = "abuse",
    notification_log_id: str = None,
    raw_payload: dict = None,
) -> dict:
    """Process a spam complaint from an ISP feedback loop."""
    from notifications.models import SpamComplaint, NotificationBlacklist, NotificationLog

    log = None
    if notification_log_id:
        try:
            log = NotificationLog.objects.get(id=notification_log_id)
        except NotificationLog.DoesNotExist:
            pass

    complaint = SpamComplaint.objects.create(
        notification_log=log,
        email_address=email_address,
        provider=provider,
        feedback_type=feedback_type,
        raw_complaint_payload=raw_payload or {},
    )

    add_to_blacklist(
        entry_type="email",
        value=email_address,
        reason=NotificationBlacklist.SuppressReason.SPAM_COMPLAINT,
        note=f"Spam complaint from {provider}",
        source_log_id=notification_log_id,
    )
    SpamComplaint.objects.filter(id=complaint.id).update(auto_blacklisted=True)

    return {
        "success": True,
        "complaint_id": str(complaint.id),
        "auto_blacklisted": True,
    }


@transaction.atomic
def register_device(
    customer,
    push_token: str,
    platform: str,
    device_model: str = "",
    os_version: str = "",
    app_version: str = "",
    device_fingerprint: str = "",
) -> object:
    """
    Register or update a push notification device token.
    If a token already exists for this fingerprint, updates it.
    If the exact token already exists, returns the existing device.
    """
    from notifications.models import CustomerDevice

    token_hash = hashlib.sha256(push_token.encode()).hexdigest()

    # Check for existing token
    existing = CustomerDevice.objects.filter(push_token_hash=token_hash).first()
    if existing:
        existing.last_seen_at = timezone.now()
        existing.save(update_fields=["last_seen_at", "updated_at"])
        return existing

    # Check for same device fingerprint (token rotation)
    if device_fingerprint:
        by_fingerprint = CustomerDevice.objects.filter(
            customer=customer,
            device_fingerprint=device_fingerprint,
            platform=platform,
        ).first()
        if by_fingerprint:
            by_fingerprint.push_token = push_token
            by_fingerprint.push_token_hash = token_hash
            by_fingerprint.status = CustomerDevice.TokenStatus.ACTIVE
            by_fingerprint.last_seen_at = timezone.now()
            by_fingerprint.save(update_fields=[
                "push_token", "push_token_hash", "status", "last_seen_at", "updated_at"
            ])
            return by_fingerprint

    return CustomerDevice.objects.create(
        customer=customer,
        push_token=push_token,
        push_token_hash=token_hash,
        platform=platform,
        device_model=device_model,
        os_version=os_version,
        app_version=app_version,
        device_fingerprint=device_fingerprint,
        status=CustomerDevice.TokenStatus.ACTIVE,
        last_seen_at=timezone.now(),
    )


def unregister_device(push_token: str = "", device_id: str = "") -> bool:
    """Deactivate a device token."""
    from notifications.models import CustomerDevice

    if push_token:
        token_hash = hashlib.sha256(push_token.encode()).hexdigest()
        updated = CustomerDevice.objects.filter(push_token_hash=token_hash).update(
            status=CustomerDevice.TokenStatus.UNREGISTERED,
            updated_at=timezone.now(),
        )
        return bool(updated)
    elif device_id:
        updated = CustomerDevice.objects.filter(id=device_id).update(
            status=CustomerDevice.TokenStatus.UNREGISTERED,
            updated_at=timezone.now(),
        )
        return bool(updated)
    return False


def get_customer_devices(customer) -> list:
    """Return all active devices for a customer."""
    from notifications.models import CustomerDevice

    devices = CustomerDevice.objects.filter(
        customer=customer,
        status=CustomerDevice.TokenStatus.ACTIVE,
    ).order_by("-registered_at")

    return [
        {
            "id": str(d.id),
            "platform": d.platform,
            "device_model": d.device_model,
            "os_version": d.os_version,
            "app_version": d.app_version,
            "is_notification_enabled": d.is_notification_enabled,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "registered_at": d.registered_at.isoformat(),
        }
        for d in devices
    ]


# ══════════════════════════════════════════════════════════════
# MODULE: webhooks.py
# Endpoint management, event dispatch, signing, retry queue
# ══════════════════════════════════════════════════════════════

@dataclass
class WebhookDispatchResult:
    success: bool = False
    attempt_id: Optional[str] = None
    endpoint_id: str = ""
    http_status: Optional[int] = None
    is_successful: bool = False
    message: str = ""
    errors: list = field(default_factory=list)


def dispatch_webhook_event(
    event_slug: str,
    event_data: dict,
    event_object_type: str = "",
    event_object_id=None,
) -> List[WebhookDispatchResult]:
    """
    Dispatch a platform event to all subscribed WebhookEndpoints.

    Returns:
        List[WebhookDispatchResult]: One result per matched endpoint.
    """
    from notifications.models import WebhookEndpoint, WebhookEventSubscription

    subscriptions = WebhookEventSubscription.objects.filter(
        is_active=True,
        endpoint__status=WebhookEndpoint.EndpointStatus.ACTIVE,
    ).filter(
        Q(event_slug=event_slug) |
        Q(event_slug="*") |
        Q(event_slug=f"{event_slug.split('.')[0]}.*")
    ).select_related("endpoint")

    results = []
    for sub in subscriptions:
        if not _passes_filter_conditions(sub.filter_conditions, event_data):
            continue

        payload = build_webhook_payload(event_slug, event_data, sub)
        result = _send_webhook_request(sub.endpoint, sub, payload, event_slug, event_object_id)
        results.append(result)

    return results


def dispatch_webhook_bulk(
    event_slug: str,
    events: List[dict],
) -> List[WebhookDispatchResult]:
    """Dispatch multiple events to webhooks (e.g. bulk inventory updates)."""
    results = []
    for event_data in events:
        batch = dispatch_webhook_event(event_slug, event_data)
        results.extend(batch)
    return results


def retry_failed_webhooks(max_retries: int = 100) -> dict:
    """
    Pick up failed webhook delivery attempts and retry them.
    Called by a scheduled Celery task every few minutes.

    Returns:
        dict: {attempted: int, succeeded: int, failed: int}
    """
    from notifications.models import WebhookDeliveryAttempt, WebhookEndpoint

    now = timezone.now()
    pending = WebhookDeliveryAttempt.objects.filter(
        is_successful=False,
        is_final_attempt=False,
        next_retry_at__lte=now,
        endpoint__status=WebhookEndpoint.EndpointStatus.ACTIVE,
    ).select_related("endpoint", "subscription")[:max_retries]

    attempted = succeeded = failed = 0

    for attempt in pending:
        attempted += 1
        result = _send_webhook_request(
            attempt.endpoint,
            attempt.subscription,
            attempt.payload,
            attempt.event_slug,
            attempt.event_object_id,
            attempt_number=attempt.attempt_number + 1,
        )
        if result.is_successful:
            succeeded += 1
        else:
            failed += 1

    return {"attempted": attempted, "succeeded": succeeded, "failed": failed}


def verify_endpoint(endpoint_id: str) -> dict:
    """
    Send a verification ping to the endpoint and mark it verified on success.

    Returns:
        dict: {success, http_status, message}
    """
    from notifications.models import WebhookEndpoint
    import time as time_module

    try:
        endpoint = WebhookEndpoint.objects.get(id=endpoint_id)
    except WebhookEndpoint.DoesNotExist:
        return {"success": False, "message": "Endpoint not found."}

    ping_payload = {
        "id": str(uuid.uuid4()),
        "event": "webhook.verification_ping",
        "created_at": timezone.now().isoformat(),
        "data": {"message": "This is a verification ping. Please respond with 200 OK."},
    }

    result = _send_webhook_request(
        endpoint=endpoint,
        subscription=None,
        payload=ping_payload,
        event_slug="webhook.verification_ping",
        event_object_id=None,
    )

    if result.is_successful:
        WebhookEndpoint.objects.filter(id=endpoint_id).update(
            is_verified=True,
            verified_at=timezone.now(),
            status=WebhookEndpoint.EndpointStatus.ACTIVE,
            updated_at=timezone.now(),
        )
        return {"success": True, "http_status": result.http_status, "message": "Endpoint verified."}

    return {
        "success": False,
        "http_status": result.http_status,
        "message": f"Verification failed: {result.message}",
    }


def create_webhook_endpoint(
    name: str,
    url: str,
    description: str = "",
    custom_headers: dict = None,
    actor=None,
    **kwargs,
) -> object:
    """Create a new WebhookEndpoint and generate its signing secret."""
    from notifications.models import WebhookEndpoint, WebhookSigningSecret

    endpoint = WebhookEndpoint.objects.create(
        name=name,
        url=url,
        description=description,
        custom_headers=custom_headers or {},
        status=WebhookEndpoint.EndpointStatus.TESTING,
        created_by=actor,
        **kwargs,
    )
    WebhookSigningSecret.generate(endpoint, created_by=actor)
    return endpoint


def update_webhook_endpoint(endpoint_id: str, actor=None, **kwargs) -> bool:
    """Update a WebhookEndpoint's fields."""
    from notifications.models import WebhookEndpoint

    updated = WebhookEndpoint.objects.filter(id=endpoint_id).update(**kwargs)
    return bool(updated)


def delete_webhook_endpoint(endpoint_id: str, actor=None) -> bool:
    """Soft-delete (disable) a webhook endpoint."""
    from notifications.models import WebhookEndpoint

    updated = WebhookEndpoint.objects.filter(id=endpoint_id).update(
        status=WebhookEndpoint.EndpointStatus.INACTIVE,
        updated_at=timezone.now(),
    )
    return bool(updated)


@transaction.atomic
def add_event_subscription(
    endpoint_id: str,
    event_slug: str,
    filter_conditions: dict = None,
    actor=None,
) -> object:
    """Subscribe an endpoint to an event."""
    from notifications.models import WebhookEndpoint, WebhookEventSubscription

    try:
        endpoint = WebhookEndpoint.objects.get(id=endpoint_id)
    except WebhookEndpoint.DoesNotExist:
        raise ValueError("Endpoint not found.")

    sub, created = WebhookEventSubscription.objects.get_or_create(
        endpoint=endpoint,
        event_slug=event_slug,
        defaults={
            "is_active": True,
            "filter_conditions": filter_conditions or {},
        },
    )
    if not created:
        sub.is_active = True
        sub.filter_conditions = filter_conditions or sub.filter_conditions
        sub.save(update_fields=["is_active", "filter_conditions", "updated_at"])
    return sub


def remove_event_subscription(endpoint_id: str, event_slug: str) -> bool:
    """Unsubscribe an endpoint from an event."""
    from notifications.models import WebhookEventSubscription

    updated = WebhookEventSubscription.objects.filter(
        endpoint_id=endpoint_id, event_slug=event_slug
    ).update(is_active=False, updated_at=timezone.now())
    return bool(updated)


@transaction.atomic
def rotate_signing_secret(endpoint_id: str, actor=None, grace_hours: int = 24) -> dict:
    """
    Rotate the signing secret for an endpoint.
    The old secret remains valid during the grace period.

    Returns:
        dict: {success, new_secret_id, new_secret_value}
    """
    from notifications.models import WebhookSigningSecret

    # Mark existing active secret as ROTATING
    WebhookSigningSecret.objects.filter(
        endpoint_id=endpoint_id,
        status=WebhookSigningSecret.SecretStatus.ACTIVE,
    ).update(
        status=WebhookSigningSecret.SecretStatus.ROTATING,
        rotated_at=timezone.now(),
        grace_period_ends_at=timezone.now() + timedelta(hours=grace_hours),
        updated_at=timezone.now(),
    )

    # Generate new secret
    from notifications.models import WebhookEndpoint
    try:
        endpoint = WebhookEndpoint.objects.get(id=endpoint_id)
    except WebhookEndpoint.DoesNotExist:
        return {"success": False, "message": "Endpoint not found."}

    new_secret = WebhookSigningSecret.generate(endpoint, created_by=actor)

    return {
        "success": True,
        "new_secret_id": str(new_secret.id),
        "new_secret_preview": new_secret.secret[:20] + "...",
        "grace_period_ends_at": (timezone.now() + timedelta(hours=grace_hours)).isoformat(),
    }


def get_endpoint_delivery_history(
    endpoint_id: str,
    page: int = 1,
    page_size: int = 20,
    success_only: bool = None,
) -> dict:
    """Return paginated delivery history for an endpoint."""
    from notifications.models import WebhookDeliveryAttempt

    qs = WebhookDeliveryAttempt.objects.filter(endpoint_id=endpoint_id).order_by("-created_at")
    if success_only is not None:
        qs = qs.filter(is_successful=success_only)

    total = qs.count()
    total_pages = math.ceil(total / page_size) if total else 1
    offset = (page - 1) * page_size

    return {
        "attempts": list(qs[offset:offset + page_size].values(
            "id", "event_slug", "attempt_number", "http_status_code",
            "is_successful", "response_time_ms", "error_type", "created_at",
        )),
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }


def verify_webhook_signature(
    endpoint_id: str,
    signature_header: str,
    timestamp: str,
    raw_body: str,
) -> bool:
    """
    Verify the HMAC-SHA256 signature on an incoming webhook request.

    Signature format: "t={timestamp},v1={hex_signature}"
    Accepts both the active signing secret and any still-in-grace rotating secrets.
    """
    from notifications.models import WebhookSigningSecret

    valid_secrets = WebhookSigningSecret.objects.filter(
        endpoint_id=endpoint_id,
    ).filter(
        Q(status=WebhookSigningSecret.SecretStatus.ACTIVE) |
        Q(
            status=WebhookSigningSecret.SecretStatus.ROTATING,
            grace_period_ends_at__gt=timezone.now(),
        )
    )

    # Parse signature header
    try:
        parts = dict(part.split("=", 1) for part in signature_header.split(","))
        provided_sig = parts.get("v1", "")
    except Exception:
        return False

    for secret in valid_secrets:
        expected = secret.compute_signature(timestamp, raw_body)
        if hmac.compare_digest(expected, provided_sig):
            return True

    return False


def build_webhook_payload(
    event_slug: str,
    event_data: dict,
    subscription=None,
) -> dict:
    """
    Build the standard webhook payload envelope.

    Format:
        {
          "id": "uuid",
          "event": "order.placed",
          "created_at": "ISO8601",
          "api_version": "2024-01",
          "data": { ... event data ... }
        }
    """
    payload = {
        "id": str(uuid.uuid4()),
        "event": event_slug,
        "created_at": timezone.now().isoformat(),
        "api_version": getattr(subscription.endpoint if subscription else None, "api_version", "2024-01"),
        "data": event_data,
    }

    if subscription:
        # Apply field inclusion/exclusion filters
        include = subscription.include_fields
        exclude = subscription.exclude_fields
        if include:
            payload["data"] = {k: v for k, v in event_data.items() if k in include}
        if exclude:
            payload["data"] = {k: v for k, v in payload["data"].items() if k not in exclude}

    return payload


def _send_webhook_request(
    endpoint,
    subscription,
    payload: dict,
    event_slug: str,
    event_object_id=None,
    attempt_number: int = 1,
) -> WebhookDispatchResult:
    """Perform the actual HTTP POST to a webhook endpoint. Stub implementation."""
    import time as time_module
    from notifications.models import WebhookDeliveryAttempt

    event_id = payload.get("id", str(uuid.uuid4()))
    timestamp = str(int(time_module.time()))
    payload_str = json.dumps(payload)

    # Get signing secret
    from notifications.models import WebhookSigningSecret
    secret = WebhookSigningSecret.objects.filter(
        endpoint=endpoint,
        status=WebhookSigningSecret.SecretStatus.ACTIVE,
    ).first()

    signature = ""
    if secret:
        sig = secret.compute_signature(timestamp, payload_str)
        signature = f"t={timestamp},v1={sig}"

    # Stub HTTP request — replace with real requests.post() call
    http_status = 200
    response_body = '{"received": true}'
    response_time_ms = 150
    is_successful = True
    error_type = ""
    error_message = ""

    # Max retries check
    is_final = attempt_number >= endpoint.max_retry_attempts
    next_retry_at = None
    if not is_successful and not is_final:
        delay = endpoint.retry_delay_seconds
        if endpoint.use_exponential_backoff:
            delay = delay * (2 ** (attempt_number - 1))
        next_retry_at = timezone.now() + timedelta(seconds=delay)

    attempt = WebhookDeliveryAttempt.objects.create(
        endpoint=endpoint,
        subscription=subscription,
        event_slug=event_slug,
        event_id=event_id,
        event_object_id=event_object_id,
        attempt_number=attempt_number,
        payload=payload,
        payload_size_bytes=len(payload_str.encode()),
        request_headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature-256": signature,
        },
        http_status_code=http_status,
        response_body=response_body[:2000],
        response_time_ms=response_time_ms,
        is_successful=is_successful,
        error_type=error_type,
        error_message=error_message,
        signature=signature,
        next_retry_at=next_retry_at,
        is_final_attempt=is_final,
    )

    if is_successful:
        endpoint.record_success()
    else:
        endpoint.record_failure()

    return WebhookDispatchResult(
        success=True,
        attempt_id=str(attempt.id),
        endpoint_id=str(endpoint.id),
        http_status=http_status,
        is_successful=is_successful,
        message=f"Delivery {'succeeded' if is_successful else 'failed'} ({http_status})",
    )


def _passes_filter_conditions(conditions: dict, event_data: dict) -> bool:
    """Check if event data satisfies filter conditions."""
    if not conditions:
        return True
    for key, condition in conditions.items():
        if key.endswith("_gte"):
            field = key[:-4]
            if float(event_data.get(field, 0)) < float(condition):
                return False
        elif key.endswith("_lte"):
            field = key[:-4]
            if float(event_data.get(field, 0)) > float(condition):
                return False
        elif event_data.get(key) != condition:
            return False
    return True


# ══════════════════════════════════════════════════════════════
# MODULE: inapp.py
# In-app notification creation, delivery, read-state management
# ══════════════════════════════════════════════════════════════

@dataclass
class InAppCreateResult:
    success: bool = False
    notification_id: Optional[str] = None
    message: str = ""
    errors: list = field(default_factory=list)


def create_inapp_notification(
    title: str,
    body: str = "",
    audience: str = "merchant",
    notification_type: str = "info",
    target_user=None,
    action_url: str = "",
    action_label: str = "",
    source_event: str = "",
    source_object_type: str = "",
    source_object_id=None,
    icon: str = "",
    expires_at=None,
    is_pinned: bool = False,
    metadata: dict = None,
    send_push: bool = False,
    send_email: bool = False,
    actor=None,
) -> InAppCreateResult:
    """
    Create an in-app notification for a specific user.

    If send_push=True, also dispatches a push notification to the user's devices.
    If send_email=True, triggers an email for critical alerts.
    """
    from notifications.models import InAppNotification, InAppNotificationRead

    notif = InAppNotification.objects.create(
        title=title,
        body=body,
        audience=audience,
        notification_type=notification_type,
        delivery_scope=InAppNotification.DeliveryScope.INDIVIDUAL,
        action_url=action_url,
        action_label=action_label,
        source_event=source_event,
        source_object_type=source_object_type,
        source_object_id=source_object_id,
        icon=icon,
        expires_at=expires_at,
        is_pinned=is_pinned,
        metadata=metadata or {},
        send_push=send_push,
        send_email=send_email,
        is_active=True,
        created_by=actor,
    )

    if target_user:
        InAppNotificationRead.objects.get_or_create(
            notification=notif,
            user=target_user,
        )

    if send_push and target_user:
        _trigger_cross_channel_push(notif, target_user)

    return InAppCreateResult(
        success=True,
        notification_id=str(notif.id),
        message="In-app notification created.",
    )


def broadcast_inapp_notification(
    title: str,
    body: str,
    audience: str = "merchant",
    notification_type: str = "info",
    target_role: str = "",
    action_url: str = "",
    expires_hours: int = 72,
    actor=None,
) -> InAppCreateResult:
    """
    Broadcast an in-app notification to all staff or all customers.
    The frontend fetches active notifications for the logged-in user on load.
    """
    from notifications.models import InAppNotification

    scope = (
        InAppNotification.DeliveryScope.ROLE if target_role
        else InAppNotification.DeliveryScope.ALL_STAFF if audience == "merchant"
        else InAppNotification.DeliveryScope.ALL_CUSTOMERS
    )

    notif = InAppNotification.objects.create(
        title=title,
        body=body,
        audience=audience,
        notification_type=notification_type,
        delivery_scope=scope,
        target_role=target_role,
        action_url=action_url,
        expires_at=timezone.now() + timedelta(hours=expires_hours),
        is_active=True,
        created_by=actor,
    )

    return InAppCreateResult(
        success=True,
        notification_id=str(notif.id),
        message=f"Broadcast notification sent (scope: {scope}).",
    )


def get_unread_notifications(user, audience: str = "merchant", limit: int = 20) -> list:
    """
    Fetch unread in-app notifications for a user.
    Returns notifications from INDIVIDUAL scope for this user
    PLUS broadcast notifications that haven't been dismissed.
    """
    from notifications.models import InAppNotification, InAppNotificationRead
    from django.db.models import Exists, OuterRef

    now = timezone.now()

    # Get dismissed notification IDs
    dismissed_ids = InAppNotificationRead.objects.filter(
        user=user, dismissed_at__isnull=False
    ).values_list("notification_id", flat=True)

    active_notifs = InAppNotification.objects.filter(
        audience=audience,
        is_active=True,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).exclude(id__in=dismissed_ids).order_by("-is_pinned", "-created_at")[:limit]

    result = []
    for notif in active_notifs:
        read_state = InAppNotificationRead.objects.filter(
            notification=notif, user=user
        ).first()
        result.append({
            "id": str(notif.id),
            "title": notif.title,
            "body": notif.body,
            "notification_type": notif.notification_type,
            "icon": notif.icon,
            "action_url": notif.action_url,
            "action_label": notif.action_label,
            "is_pinned": notif.is_pinned,
            "is_read": read_state.read_at is not None if read_state else False,
            "is_dismissed": read_state.dismissed_at is not None if read_state else False,
            "created_at": notif.created_at.isoformat(),
            "expires_at": notif.expires_at.isoformat() if notif.expires_at else None,
            "metadata": notif.metadata,
        })

    return result


def get_notification_feed(user, audience: str = "merchant", page: int = 1, page_size: int = 20) -> dict:
    """Paginated notification history for the notification bell dropdown."""
    from notifications.models import InAppNotification

    now = timezone.now()
    qs = InAppNotification.objects.filter(
        audience=audience, is_active=True,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).order_by("-is_pinned", "-created_at")

    total = qs.count()
    total_pages = math.ceil(total / page_size) if total else 1
    offset = (page - 1) * page_size

    return {
        "notifications": get_unread_notifications(user, audience, page_size),
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "unread_count": get_unread_count(user, audience),
    }


def mark_notification_read(notification_id: str, user, ip_address: str = "") -> bool:
    """Mark a notification as read for a user."""
    from notifications.models import InAppNotification, InAppNotificationRead

    try:
        notif = InAppNotification.objects.get(id=notification_id)
    except InAppNotification.DoesNotExist:
        return False

    state, _ = InAppNotificationRead.objects.get_or_create(
        notification=notif, user=user
    )
    state.mark_read(ip_address)
    return True


def mark_notification_dismissed(notification_id: str, user) -> bool:
    """Dismiss a notification for a user."""
    from notifications.models import InAppNotification, InAppNotificationRead

    try:
        notif = InAppNotification.objects.get(id=notification_id)
    except InAppNotification.DoesNotExist:
        return False

    if notif.is_pinned:
        return False

    state, _ = InAppNotificationRead.objects.get_or_create(
        notification=notif, user=user
    )
    state.mark_dismissed()
    return True


def mark_notification_actioned(notification_id: str, user, url: str = "") -> bool:
    """Mark a notification as actioned when user clicks the action button."""
    from notifications.models import InAppNotification, InAppNotificationRead

    try:
        notif = InAppNotification.objects.get(id=notification_id)
    except InAppNotification.DoesNotExist:
        return False

    state, _ = InAppNotificationRead.objects.get_or_create(
        notification=notif, user=user
    )
    state.mark_actioned(url)
    return True


def mark_all_read(user, audience: str = "merchant") -> int:
    """Mark all unread notifications as read for a user. Returns count marked."""
    from notifications.models import InAppNotification, InAppNotificationRead

    now = timezone.now()
    active_ids = InAppNotification.objects.filter(
        audience=audience, is_active=True,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).values_list("id", flat=True)

    count = 0
    for notif_id in active_ids:
        state, created = InAppNotificationRead.objects.get_or_create(
            notification_id=notif_id, user=user,
            defaults={"read_at": timezone.now()},
        )
        if not created and not state.read_at:
            state.mark_read()
            count += 1
        elif created:
            count += 1

    return count


def get_unread_count(user, audience: str = "merchant") -> int:
    """Get unread notification count for the bell badge."""
    from notifications.models import InAppNotification, InAppNotificationRead
    from django.db.models import Exists, OuterRef

    now = timezone.now()
    read_subq = InAppNotificationRead.objects.filter(
        notification=OuterRef("pk"),
        user=user,
        read_at__isnull=False,
    )

    return InAppNotification.objects.filter(
        audience=audience,
        is_active=True,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).annotate(is_read=Exists(read_subq)).filter(is_read=False).count()


def delete_expired_notifications() -> int:
    """
    Mark expired InAppNotifications as inactive.
    Called by a scheduled Celery task.
    """
    from notifications.models import InAppNotification

    expired = InAppNotification.objects.filter(
        is_active=True,
        expires_at__lt=timezone.now(),
    )
    count = expired.count()
    expired.update(is_active=False, updated_at=timezone.now())
    return count


def _trigger_cross_channel_push(notification, user) -> None:
    """Trigger a push notification alongside an in-app notification."""
    logger.debug(
        "Cross-channel push triggered for in-app notification %s to user %s",
        notification.id, user,
    )
