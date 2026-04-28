from __future__ import annotations

import logging
from pathlib import Path

from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.shortcuts import render
from django.template import Context, Template
from django.template.exceptions import TemplateDoesNotExist

from system.theme_marketplace.services import (
    DEFAULT_THEME_SLUG,
    clear_active_theme_cache as clear_shared_active_theme_cache,
    has_active_theme_for_schema,
    get_theme_slug_for_schema,
    get_themes_root,
)

logger = logging.getLogger(__name__)


def get_active_theme_cache_key(schema_name):
    normalized_schema = str(schema_name or "public")
    return f"sabistart:theme:active:{normalized_schema}"


def clear_active_theme_cache(schema_name):
    clear_shared_active_theme_cache(str(schema_name or "public"))


def get_active_theme_for_shop(schema_name):
    """
    Compatibility wrapper for older callers.

    The shared theme system now resolves themes by tenant schema name instead of shop-id
    folder copies.
    """
    return get_theme_slug_for_schema(str(schema_name or "public"))


def template_exists(template_name: str) -> bool:
    from django.template.loader import get_template

    if not template_name or not isinstance(template_name, str):
        return False
    if ".." in template_name or template_name.startswith("/"):
        return False
    try:
        get_template(template_name)
        return True
    except TemplateDoesNotExist:
        return False
    except Exception:
        return False


def render_theme_template(request, template_name, context=None, fallback_context=None):
    """Render storefront templates through the shared theme loader with safe fallback."""
    if not template_name or not isinstance(template_name, str):
        logger.error("Invalid template name provided to render_theme_template")
        return _render_fallback_template(context or fallback_context or {})

    if ".." in template_name or template_name.startswith("/"):
        logger.warning("Directory traversal attempt blocked: %s", template_name)
        raise SuspiciousOperation("Invalid template name")

    if not template_name.endswith((".html", ".htm", ".xml")):
        template_name += ".html"

    safe_context = _sanitize_context(context or {})
    if fallback_context:
        safe_context.update(_sanitize_context(fallback_context))

    schema_name = "public"
    try:
        tenant = getattr(request, "tenant", None)
        schema_name = str(getattr(tenant, "schema_name", None) or "public")
    except Exception:
        schema_name = "public"

    if schema_name != "public" and not has_active_theme_for_schema(schema_name):
        return _render_setup_required_template(safe_context)

    try:
        return render(request, template_name, safe_context)
    except TemplateDoesNotExist:
        logger.warning("No storefront template found for %s; using emergency fallback.", template_name)
        return _render_fallback_template(safe_context)
    except SuspiciousOperation:
        raise
    except Exception as exc:
        logger.error("Critical error in render_theme_template: %s", exc, exc_info=True)
        return _render_fallback_template(safe_context)


def get_theme_template_path(schema_name, template_name):
    """Compatibility helper for preview/debug flows in the shared theme system."""
    theme_slug = get_theme_slug_for_schema(str(schema_name or "public"))
    themes_root = get_themes_root()
    candidates = [
        themes_root / theme_slug / "templates" / template_name,
        themes_root / DEFAULT_THEME_SLUG / "templates" / template_name,
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def _sanitize_context(context):
    if not isinstance(context, dict):
        context = {"data": context} if context is not None else {}

    sanitized = {}
    dangerous_keys = ["request", "settings", "os", "sys", "django", "import", "__"]
    for key, value in context.items():
        key = str(key)
        if any(dangerous in key.lower() for dangerous in dangerous_keys):
            continue
        if isinstance(value, str) and len(value) > 10000:
            value = value[:10000] + "... [truncated]"
        sanitized[key] = value
    return sanitized


def _render_fallback_template(context):
    try:
        fallback_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>{% if shop and shop.name %}{{ shop.name|escape }}{% else %}Store{% endif %}</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>{% if shop and shop.name %}<a href="/">{{ shop.name|escape }}</a>{% else %}Welcome{% endif %}</h1>
                </header>
                <main>
                    <p>Page is loading...</p>
                    {% if message %}<p class="message">{{ message|escape }}</p>{% endif %}
                </main>
                <footer>
                    <p>Theme system is working</p>
                </footer>
            </div>
        </body>
        </html>
        """
        template = Template(fallback_html)
        rendered = template.render(Context(_sanitize_context(context or {})))
        return HttpResponse(rendered)
    except Exception as exc:
        logger.error("Fallback template rendering failed: %s", exc)
        return HttpResponse(
            "<!DOCTYPE html><html><head><title>Store</title></head><body><h1>Service Temporarily Unavailable</h1><p>Please try again later.</p></body></html>",
            status=503,
        )


def _render_setup_required_template(context):
    safe_context = _sanitize_context(context or {})
    try:
        template = Template(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Theme setup required</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body{font-family:Arial,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:3rem;}
                    .card{max-width:56rem;margin:0 auto;background:#fff;border:1px solid #e2e8f0;border-radius:2rem;padding:2.5rem;box-shadow:0 10px 40px rgba(15,23,42,.08)}
                    .eyebrow{font-size:.75rem;letter-spacing:.28em;text-transform:uppercase;color:#2563eb;font-weight:700}
                    h1{font-size:2rem;margin:.75rem 0 1rem}
                    p{line-height:1.7;color:#475569}
                </style>
            </head>
            <body>
                <div class="card">
                    <p class="eyebrow">Storefront setup</p>
                    <h1>This storefront needs an active theme</h1>
                    <p>The tenant has not acquired, installed, and activated a storefront theme yet. Go to the dashboard theme marketplace, acquire a theme, install it, configure its content, and activate it before publishing the storefront.</p>
                </div>
            </body>
            </html>
            """
        )
        return HttpResponse(template.render(Context(safe_context)))
    except Exception:
        return HttpResponse(
            "<!DOCTYPE html><html><head><title>Theme setup required</title></head><body><h1>Theme setup required</h1><p>This storefront needs an active theme before it can be published.</p></body></html>",
            status=200,
        )
