from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from sabistart_store.navigation import build_platform_navigation
from system.account.platform_support import safe_platform_call, setup_warning_for
from system.theme_marketplace.forms import ThemeCategoryForm, ThemeForm
from system.theme_marketplace.models import Theme, ThemeBasePage, ThemeCategory
from system.theme_marketplace.services import (
    shared_theme_manifest_exists,
    sync_theme_catalog,
)


def _is_platform_staff(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff or getattr(user, "is_platform_admin", False))


def platform_staff_required(view_func):
    return login_required(user_passes_test(_is_platform_staff)(view_func), login_url="platform:login")


THEME_NAV = (
    {"key": "platform_themes", "label": "Overview", "route": "platform_themes:home"},
    {"key": "platform_themes_catalog", "label": "Catalog", "route": "platform_themes:home"},
    {"key": "platform_themes_categories", "label": "Categories", "route": "platform_themes:categories"},
    {"key": "platform_themes_create", "label": "Add Theme", "route": "platform_themes:create"},
)

THEME_SHARED_MODELS = (
    ThemeCategory,
    Theme,
    ThemeBasePage,
)


def _theme_nav(active_key: str):
    from django.urls import reverse

    return [{**item, "url": reverse(item["route"]), "active": item["key"] == active_key} for item in THEME_NAV]


def _theme_context(request, *, page_title: str, active_key: str = "platform_themes", **extra):
    context = {
        "page_title": page_title,
        "active_platform_nav": "platform_themes",
        "platform_navigation": build_platform_navigation("platform_themes"),
        "theme_navigation": _theme_nav(active_key),
        "theme_count": safe_platform_call(lambda: Theme.objects.count(), 0),
        "published_count": safe_platform_call(lambda: Theme.objects.filter(is_published=True).count(), 0),
        "category_count": safe_platform_call(lambda: ThemeCategory.objects.count(), 0),
        "setup_warning": setup_warning_for("Theme marketplace", *THEME_SHARED_MODELS),
    }
    context.update(extra)
    return context


@platform_staff_required
def home(request):
    setup_warning = setup_warning_for("Theme marketplace", *THEME_SHARED_MODELS)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    themes = safe_platform_call(
        lambda: Theme.objects.select_related("category", "creator").order_by("-is_featured", "-published_at", "-created_at"),
        Theme.objects.none,
    )
    if q:
        themes = themes.filter(name__icontains=q)
    if status:
        themes = themes.filter(status=status)
    themes = [theme for theme in themes if shared_theme_manifest_exists(theme.slug)]
    context = _theme_context(
        request,
        page_title="Theme Marketplace",
        setup_warning=setup_warning,
        themes=themes,
        q=q,
        status=status,
        categories=safe_platform_call(
            lambda: ThemeCategory.objects.filter(is_active=True).order_by("sort_order", "name"),
            ThemeCategory.objects.none,
        ),
    )
    return render(request, "account/themes/index.html", context)


@platform_staff_required
def create(request):
    setup_warning = setup_warning_for("Theme marketplace", *THEME_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_themes:home")
    form = ThemeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        theme = form.save(commit=False)
        theme.creator = request.user
        theme.save()
        messages.success(request, "Theme saved.")
        return redirect("platform_themes:detail", theme_id=theme.id)
    context = _theme_context(request, page_title="Add Theme", active_key="platform_themes_create", form=form)
    return render(request, "account/themes/form.html", context)


@platform_staff_required
def detail(request, theme_id):
    setup_warning = setup_warning_for("Theme marketplace", *THEME_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_themes:home")
    theme = get_object_or_404(Theme.objects.select_related("category", "creator").prefetch_related("base_pages"), pk=theme_id)
    if not shared_theme_manifest_exists(theme.slug):
        messages.error(request, "That legacy theme no longer has a shared directory backing it.")
        return redirect("platform_themes:home")
    form = ThemeForm(request.POST or None, request.FILES or None, instance=theme)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "save" and form.is_valid():
            theme = form.save(commit=False)
            theme.save()
            messages.success(request, "Theme updated.")
            return redirect("platform_themes:detail", theme_id=theme.id)
        if action == "approve":
            theme.status = "approved"
            theme.save(update_fields=["status", "updated_at"])
            messages.success(request, "Theme approved.")
            return redirect("platform_themes:detail", theme_id=theme.id)
        if action == "publish":
            theme.status = "approved"
            theme.is_published = True
            theme.save(update_fields=["status", "is_published", "updated_at"])
            messages.success(request, "Theme published.")
            return redirect("platform_themes:detail", theme_id=theme.id)
        if action == "unpublish":
            theme.is_published = False
            theme.save(update_fields=["is_published", "updated_at"])
            messages.info(request, "Theme unpublished.")
            return redirect("platform_themes:detail", theme_id=theme.id)
        if action == "suspend":
            theme.status = "suspended"
            theme.is_published = False
            theme.save(update_fields=["status", "is_published", "updated_at"])
            messages.warning(request, "Theme suspended.")
            return redirect("platform_themes:detail", theme_id=theme.id)
    context = _theme_context(
        request,
        page_title=theme.name,
        form=form,
        theme=theme,
        base_pages=theme.base_pages.all(),
    )
    return render(request, "account/themes/detail.html", context)


@platform_staff_required
def categories(request):
    setup_warning = setup_warning_for("Theme marketplace", *THEME_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_themes:home")
    editing = None
    if request.GET.get("edit"):
        editing = get_object_or_404(ThemeCategory, pk=request.GET["edit"])
    form = ThemeCategoryForm(request.POST or None, instance=editing)
    if request.method == "POST":
        if "delete" in request.POST:
            category = get_object_or_404(ThemeCategory, pk=request.POST.get("category_id"))
            if category.themes.exists():
                messages.error(request, "Move themes out of this category before deleting it.")
            else:
                category.delete()
                messages.success(request, "Theme category deleted.")
            return redirect("platform_themes:categories")
        if form.is_valid():
            form.save()
            messages.success(request, "Theme category saved.")
            return redirect("platform_themes:categories")
    categories_qs = ThemeCategory.objects.annotate(theme_count=Count("themes")).order_by("sort_order", "name")
    context = _theme_context(
        request,
        page_title="Theme Categories",
        active_key="platform_themes_categories",
        form=form,
        categories=categories_qs,
        editing=editing,
    )
    return render(request, "account/themes/categories.html", context)


@platform_staff_required
def sync_catalog(request):
    setup_warning = setup_warning_for("Theme marketplace", *THEME_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_themes:home")
    if request.method == "POST":
        result = sync_theme_catalog(actor=request.user, bootstrap_access=True)
        messages.success(
            request,
            f"Synced theme catalog. Created {result['created']} themes, updated {result['updated']}, and synced {result['pages_synced']} theme pages.",
        )
    return redirect("platform_themes:home")
