from django.http import Http404

from dashboard.store_settings.content_services import get_public_managed_page
from public.storefront.services import build_breadcrumbs, render_storefront


def _render_managed_page(request, *, page_kind: str, title: str, breadcrumb_label: str):
    page = get_public_managed_page(page_kind)
    if page is None:
        raise Http404("This page is not available.")
    return render_storefront(
        request,
        "shared/content_page.html",
        {
            "page": page,
            "headline": page.title if page.show_title else title,
            "breadcrumbs": build_breadcrumbs(("Home", "/"), (breadcrumb_label, "")) if page.show_breadcrumbs else [],
        },
        page_title=page.meta_title or page.title,
        page_description=page.meta_description or page.excerpt or title,
    )


def terms_of_service_view(request):
    return _render_managed_page(request, page_kind="terms_of_service", title="Terms of Service", breadcrumb_label="Terms")


def privacy_policy_view(request):
    return _render_managed_page(request, page_kind="privacy_policy", title="Privacy Policy", breadcrumb_label="Privacy")


def cookie_policy_view(request):
    return _render_managed_page(request, page_kind="cookie_policy", title="Cookie Policy", breadcrumb_label="Cookies")


def dmca_policy_view(request):
    return _render_managed_page(request, page_kind="dmca_policy", title="DMCA Policy", breadcrumb_label="DMCA")


def accessibility_statement_view(request):
    return _render_managed_page(request, page_kind="accessibility_statement", title="Accessibility", breadcrumb_label="Accessibility")


def modern_slavery_statement_view(request):
    return _render_managed_page(request, page_kind="modern_slavery_statement", title="Modern Slavery Statement", breadcrumb_label="Modern Slavery")


def compliance_view(request):
    return _render_managed_page(request, page_kind="compliance_notice", title="Compliance", breadcrumb_label="Compliance")


def cookie_preferences_view(request):
    return _render_managed_page(request, page_kind="cookie_preferences", title="Cookie Preferences", breadcrumb_label="Cookie Preferences")
