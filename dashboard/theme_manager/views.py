from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.sidebar_utiles import main_sidebar
from dashboard.theme_manager.forms import TenantThemeConfigureForm
from dashboard.theme_manager.utils import clear_active_theme_cache
from system.theme_marketplace.models import TenantActiveTheme, TenantInstalledTheme, TenantThemeContent, TenantThemeAccess, Theme, ThemeCategory
from system.theme_marketplace.services import (
    acquire_theme_for_schema,
    activate_theme_for_schema,
    configure_theme_content_for_schema,
    deactivate_theme_for_schema,
    disable_installed_theme_for_schema,
    has_active_theme_for_schema,
    install_theme_for_schema,
    list_listed_themes,
    remove_theme_for_schema,
    shared_theme_manifest_exists,
)


def _schema_name(request) -> str:
    tenant = getattr(request, "tenant", None)
    return str(getattr(tenant, "schema_name", None) or "public")


def _ctx(prefix: str, page_title: str, active_menu: str = "store_theme", **extra):
    context = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix, active_menu),
    }
    context.update(extra)
    return context


def _theme_or_404(theme_id):
    theme = get_object_or_404(
        Theme.objects.select_related("category", "creator").prefetch_related("base_pages", "offers", "releases", "reviews"),
        pk=theme_id,
        is_published=True,
        status=Theme.Status.APPROVED,
        is_internal=False,
    )
    if not shared_theme_manifest_exists(theme.slug):
        raise Http404("That theme is no longer available from the shared theme catalog.")
    return theme


@dashboard_prefix_required
@login_required
def marketplace(request, prefix):
    schema_name = _schema_name(request)
    search_query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()
    themes = list_listed_themes()
    if search_query:
        themes = themes.filter(name__icontains=search_query)
    if category_slug:
        themes = themes.filter(category__slug=category_slug)
    themes = [theme for theme in themes.order_by("-is_featured", "-published_at", "-created_at") if shared_theme_manifest_exists(theme.slug)]
    access_ids = set(
        TenantThemeAccess.objects.filter(schema_name=schema_name, is_active=True).values_list("theme_id", flat=True)
    )
    installed_ids = set(
        TenantInstalledTheme.objects.filter(
            schema_name=schema_name,
            install_status=TenantInstalledTheme.InstallStatus.INSTALLED,
        ).values_list("theme_id", flat=True)
    )
    active_theme = TenantActiveTheme.objects.filter(schema_name=schema_name).select_related("theme").first()
    context = _ctx(
        prefix,
        "Theme Marketplace",
        active_menu="store_theme_marketplace",
        categories=ThemeCategory.objects.filter(is_active=True).order_by("sort_order", "name"),
        themes=themes,
        acquired_ids=access_ids,
        installed_ids=installed_ids,
        active_theme=active_theme,
        has_active_theme=has_active_theme_for_schema(schema_name),
        search_query=search_query,
        category_slug=category_slug,
    )
    return render(request, "dashboard/theme_manager/marketplace.html", context)


@dashboard_prefix_required
@login_required
def theme_detail(request, prefix, theme_id):
    schema_name = _schema_name(request)
    theme = _theme_or_404(theme_id)
    access = TenantThemeAccess.objects.filter(schema_name=schema_name, theme_id=theme.id, is_active=True).first()
    installed = TenantInstalledTheme.objects.filter(
        schema_name=schema_name,
        theme_id=theme.id,
        install_status=TenantInstalledTheme.InstallStatus.INSTALLED,
    ).first()
    active_theme = TenantActiveTheme.objects.filter(schema_name=schema_name).select_related("theme").first()
    content_record = TenantThemeContent.objects.filter(schema_name=schema_name, theme=theme).first()
    context = _ctx(
        prefix,
        theme.name,
        active_menu="store_theme_marketplace",
        theme=theme,
        access_record=access,
        installed_theme=installed,
        active_theme=active_theme,
        theme_content=content_record,
    )
    return render(request, "dashboard/theme_manager/detail.html", context)


@dashboard_prefix_required
@login_required
@require_http_methods(["POST"])
def acquire_theme(request, prefix, theme_id):
    theme = _theme_or_404(theme_id)
    schema_name = _schema_name(request)
    if TenantThemeAccess.objects.filter(schema_name=schema_name, theme=theme, is_active=True).exists():
        messages.info(request, "You already acquired this theme.")
        return redirect("dashboard:themes:theme_detail", prefix=prefix, theme_id=theme.id)
    if not theme.is_free:
        messages.error(request, "Paid theme checkout is not wired into this tenant flow yet.")
        return redirect("dashboard:themes:theme_detail", prefix=prefix, theme_id=theme.id)
    acquire_theme_for_schema(schema_name, theme, actor=request.user)
    Theme.objects.filter(pk=theme.pk).update(downloads=theme.downloads + 1)
    messages.success(request, f'"{theme.name}" has been added to your theme library.')
    return redirect("dashboard:themes:theme_detail", prefix=prefix, theme_id=theme.id)


@dashboard_prefix_required
@login_required
@require_http_methods(["POST"])
def install_theme(request, prefix, theme_id):
    theme = _theme_or_404(theme_id)
    schema_name = _schema_name(request)
    try:
        install_theme_for_schema(schema_name, theme)
        messages.success(request, f'"{theme.name}" is now installed and ready to configure.')
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:themes:theme_detail", prefix=prefix, theme_id=theme.id)
    return redirect("dashboard:themes:configure", prefix=prefix, theme_id=theme.id)


@dashboard_prefix_required
@login_required
def installed_themes(request, prefix):
    schema_name = _schema_name(request)
    themes = list(
        TenantInstalledTheme.objects.filter(
            schema_name=schema_name,
            install_status__in=[TenantInstalledTheme.InstallStatus.INSTALLED, TenantInstalledTheme.InstallStatus.DISABLED],
        )
        .select_related("theme", "theme__category", "theme__creator")
        .prefetch_related("theme__base_pages")
        .order_by("-theme__is_featured", "theme__name")
    )
    active_theme = TenantActiveTheme.objects.filter(schema_name=schema_name).select_related("theme").first()
    context = _ctx(
        prefix,
        "Installed Themes",
        active_menu="store_theme_installed",
        themes=themes,
        active_theme=active_theme,
        has_active_theme=active_theme is not None,
    )
    return render(request, "dashboard/theme_manager/installed.html", context)


@dashboard_prefix_required
@login_required
def configure_theme(request, prefix, theme_id):
    schema_name = _schema_name(request)
    theme = _theme_or_404(theme_id)
    installed = TenantInstalledTheme.objects.filter(
        schema_name=schema_name,
        theme=theme,
        install_status=TenantInstalledTheme.InstallStatus.INSTALLED,
    ).first()
    if installed is None:
        messages.error(request, "Install this theme before configuring it.")
        return redirect("dashboard:themes:theme_detail", prefix=prefix, theme_id=theme.id)
    schema = theme.metadata.get("theme_schema", {}) or {}
    record = TenantThemeContent.objects.filter(schema_name=schema_name, theme=theme).first()
    form = TenantThemeConfigureForm(request.POST or None, theme_schema=schema)
    if record is not None and request.method != "POST":
        form.initial_from_content(record.universal_content or {}, record.theme_content or {})
    if request.method == "POST" and form.is_valid():
        universal_content, theme_content = form.build_content_payloads()
        configure_theme_content_for_schema(
            schema_name,
            theme,
            universal_content=universal_content,
            theme_content=theme_content,
        )
        messages.success(request, "Theme content saved.")
        return redirect("dashboard:themes:theme_detail", prefix=prefix, theme_id=theme.id)
    context = _ctx(
        prefix,
        f"Configure {theme.name}",
        active_menu="store_theme_installed",
        form=form,
        theme=theme,
        theme_schema=schema,
        installed_theme=installed,
    )
    return render(request, "dashboard/theme_manager/configure.html", context)


@dashboard_prefix_required
@login_required
@require_http_methods(["POST"])
def activate_theme(request, prefix, theme_id):
    schema_name = _schema_name(request)
    theme = _theme_or_404(theme_id)
    try:
        activate_theme_for_schema(schema_name, theme, actor=request.user, reason="tenant_activation")
        clear_active_theme_cache(schema_name)
        messages.success(request, f'"{theme.name}" is now active.')
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:themes:theme_detail", prefix=prefix, theme_id=theme.id)
    return redirect("dashboard:themes:installed", prefix=prefix)


@dashboard_prefix_required
@login_required
@require_http_methods(["POST"])
def deactivate_theme(request, prefix, theme_id):
    schema_name = _schema_name(request)
    theme = _theme_or_404(theme_id)
    deactivate_theme_for_schema(schema_name, actor=request.user, reason="tenant_deactivation")
    clear_active_theme_cache(schema_name)
    messages.success(request, f'"{theme.name}" has been deactivated. Publish stays blocked until another theme is active.')
    return redirect("dashboard:themes:installed", prefix=prefix)


@dashboard_prefix_required
@login_required
@require_http_methods(["POST"])
def disable_theme(request, prefix, theme_id):
    schema_name = _schema_name(request)
    theme = _theme_or_404(theme_id)
    try:
        disable_installed_theme_for_schema(schema_name, theme)
        messages.success(request, f'"{theme.name}" has been disabled.')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:themes:installed", prefix=prefix)


@dashboard_prefix_required
@login_required
@require_http_methods(["POST"])
def remove_theme(request, prefix, theme_id):
    schema_name = _schema_name(request)
    theme = _theme_or_404(theme_id)
    try:
        remove_theme_for_schema(schema_name, theme)
        messages.success(request, f'"{theme.name}" has been removed from this store.')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:themes:installed", prefix=prefix)


@dashboard_prefix_required
@login_required
def page_editor(request, prefix, theme_id, page_name):
    raise Http404("Tenant file-based theme editing is disabled in the shared theme architecture.")


@dashboard_prefix_required
@login_required
def preview_theme(request, prefix, theme_id, page_name="home"):
    raise Http404("Tenant file-based theme preview is disabled in the shared theme architecture.")
