import os

from django import template
from django.conf import settings
from django.templatetags.static import static

from dashboard.theme_manager.utils import get_active_theme_for_shop

register = template.Library()


def _resolve_schema_name(request) -> str:
    tenant = getattr(request, "tenant", None)
    return str(
        getattr(tenant, "schema_name", None)
        or "public"
    )


@register.simple_tag(takes_context=True)
def theme_static(context, path):
    """Resolve shared-theme static assets without probing per-tenant copies."""
    request = context.get("request")
    if not request:
        return static(path)

    schema_name = _resolve_schema_name(request)
    theme_name = get_active_theme_for_shop(schema_name)

    candidate_paths = [
        f"{theme_name}/{path}",
        f"default/{path}",
    ]

    for candidate in candidate_paths:
        parts = candidate.split("/")
        full_path = os.path.join(settings.THEMES_ROOT, parts[0], "static", *parts)
        if os.path.exists(full_path):
            return static(candidate)

    return static(path)


@register.simple_tag(takes_context=True)
def current_theme_name(context):
    """Return the resolved theme slug for the current tenant."""
    request = context.get("request")
    if not request:
        return "default"

    return get_active_theme_for_shop(_resolve_schema_name(request))
