from __future__ import annotations

from dataclasses import dataclass

from django.http import Http404
from django.urls import reverse

from dashboard.store_settings.models import BlogPost, BlogSettings, CustomPage, FAQEntry


@dataclass(frozen=True)
class ManagedPageDefinition:
    key: str
    title: str
    route_name: str
    section: str
    description: str
    default_body: str
    default_excerpt: str = ""
    template: str = "narrow"
    icon: str = "description"


MANAGED_PAGE_DEFINITIONS: tuple[ManagedPageDefinition, ...] = (
    ManagedPageDefinition(
        key="privacy_policy",
        title="Privacy Policy",
        route_name="legal:privacy_policy",
        section="Legal",
        icon="privacy_tip",
        description="Control the privacy page shown to storefront visitors.",
        default_body="Explain what customer data you collect, how you use it, and how customers can contact you about privacy concerns.",
        default_excerpt="How your store collects and handles customer information.",
    ),
    ManagedPageDefinition(
        key="terms_of_service",
        title="Terms & Conditions",
        route_name="legal:terms_of_service",
        section="Legal",
        icon="gavel",
        description="Publish your storefront terms, rules, and legal conditions.",
        default_body="Set out the rules for using your store, placing orders, returns, disputes, and any store-specific legal conditions.",
        default_excerpt="Your store's terms, rules, and buying conditions.",
    ),
    ManagedPageDefinition(
        key="cookie_policy",
        title="Cookie Policy",
        route_name="legal:cookie_policy",
        section="Legal",
        icon="cookie",
        description="Explain how cookies and tracking tools are used on your store.",
        default_body="Describe the cookies, analytics, and tracking technologies your store uses, including how visitors can manage them.",
        default_excerpt="How your store uses cookies and related tracking tools.",
    ),
    ManagedPageDefinition(
        key="dmca_policy",
        title="DMCA Policy",
        route_name="legal:dmca_policy",
        section="Legal",
        icon="report",
        description="Provide copyright and infringement reporting instructions.",
        default_body="Explain how copyright complaints should be submitted and how your store handles infringement claims.",
        default_excerpt="Copyright and infringement reporting process.",
    ),
    ManagedPageDefinition(
        key="accessibility_statement",
        title="Accessibility Statement",
        route_name="legal:accessibility",
        section="Legal",
        icon="accessible",
        description="Describe your store's accessibility commitments.",
        default_body="Share how your store is working to support accessible browsing and how customers can report barriers.",
        default_excerpt="Your accessibility commitments for storefront visitors.",
    ),
    ManagedPageDefinition(
        key="modern_slavery_statement",
        title="Modern Slavery Statement",
        route_name="legal:slavery_statement",
        section="Legal",
        icon="policy",
        description="Publish a compliance or ethical sourcing statement if needed.",
        default_body="Explain your business practices around ethical sourcing, labor protections, and compliance commitments where relevant.",
        default_excerpt="Ethical sourcing and modern slavery compliance statement.",
    ),
    ManagedPageDefinition(
        key="compliance_notice",
        title="Compliance Notice",
        route_name="legal:compliance",
        section="Legal",
        icon="verified_user",
        description="Share regulatory, tax, or operational compliance notices.",
        default_body="Use this page for regulatory notices, licensing details, or other important compliance information for customers.",
        default_excerpt="Regulatory and operational compliance information.",
    ),
    ManagedPageDefinition(
        key="cookie_preferences",
        title="Cookie Preferences",
        route_name="legal:cookie_preferences",
        section="Legal",
        icon="tune",
        description="Add customer guidance around cookie preferences and tracking controls.",
        default_body="Use this page to explain how visitors can manage cookie preferences and tracking choices in your storefront.",
        default_excerpt="How visitors can review and manage cookie preferences.",
    ),
    ManagedPageDefinition(
        key="help_center",
        title="Help Center",
        route_name="support:help_center",
        section="Support",
        icon="help_center",
        description="Control the public help center and FAQ landing page.",
        default_body="Welcome visitors to your help center. You can answer common questions below and publish quick support guidance for customers.",
        default_excerpt="Frequently asked questions and store support information.",
        template="faq",
    ),
    ManagedPageDefinition(
        key="delivery_information",
        title="Delivery Information",
        route_name="support:delivery_info",
        section="Support",
        icon="local_shipping",
        description="Explain shipping, delivery timelines, and fulfillment expectations.",
        default_body="Use this page to share your delivery zones, timelines, shipping methods, and any important fulfillment notes.",
        default_excerpt="Shipping timelines, delivery coverage, and fulfillment guidance.",
    ),
    ManagedPageDefinition(
        key="returns_policy",
        title="Returns Policy",
        route_name="support:returns_policy",
        section="Support",
        icon="assignment_return",
        description="Publish your returns and exchange policy for shoppers.",
        default_body="Explain your return window, exchange rules, refund process, and any non-returnable items or conditions.",
        default_excerpt="Rules for returns, exchanges, and refunds.",
    ),
    ManagedPageDefinition(
        key="warranty_information",
        title="Warranty Information",
        route_name="support:warranty_info",
        section="Support",
        icon="shield",
        description="Provide warranty terms for supported products or categories.",
        default_body="Use this page to explain warranty coverage, exclusions, claim steps, and any important after-sales support details.",
        default_excerpt="Warranty coverage and claim instructions for customers.",
    ),
)

MANAGED_PAGE_LOOKUP = {definition.key: definition for definition in MANAGED_PAGE_DEFINITIONS}


def get_managed_page_definition(page_kind: str) -> ManagedPageDefinition:
    return MANAGED_PAGE_LOOKUP[page_kind]


def get_or_create_blog_settings() -> BlogSettings:
    settings = BlogSettings.objects.first()
    if settings is None:
        settings = BlogSettings.objects.create()
    return settings


def get_or_create_managed_page(page_kind: str) -> CustomPage:
    definition = get_managed_page_definition(page_kind)
    page, _created = CustomPage.objects.get_or_create(
        page_kind=page_kind,
        defaults={
            "title": definition.title,
            "slug": f"managed-{page_kind.replace('_', '-')}",
            "content": definition.default_body,
            "excerpt": definition.default_excerpt,
            "template": definition.template,
            "status": "published",
            "is_enabled": True,
            "meta_title": definition.title,
            "meta_description": definition.default_excerpt or definition.description,
        },
    )
    needs_save = False
    if not page.slug:
        page.slug = f"managed-{page_kind.replace('_', '-')}"
        needs_save = True
    if page.page_kind != page_kind:
        page.page_kind = page_kind
        needs_save = True
    if needs_save:
        page.save()
    return page


def list_managed_pages() -> list[tuple[ManagedPageDefinition, CustomPage, str]]:
    pages: list[tuple[ManagedPageDefinition, CustomPage, str]] = []
    for definition in MANAGED_PAGE_DEFINITIONS:
        page = get_or_create_managed_page(definition.key)
        pages.append((definition, page, reverse(definition.route_name)))
    return pages


def get_managed_page_or_404(page_kind: str) -> CustomPage:
    page = get_or_create_managed_page(page_kind)
    if not page.is_enabled or page.status != "published":
        raise Http404("This page is not available.")
    return page


def get_public_managed_page(page_kind: str) -> CustomPage | None:
    page = get_or_create_managed_page(page_kind)
    if not page.is_enabled or page.status != "published":
        return None
    return page


def get_public_custom_page(page_slug: str) -> CustomPage | None:
    try:
        page = CustomPage.objects.get(slug=page_slug, page_kind="generic")
    except CustomPage.DoesNotExist:
        return None
    if page.status != "published" or not page.is_enabled:
        return None
    return page


def get_public_blog_posts():
    settings = get_or_create_blog_settings()
    if not settings.enable_blog:
        return settings, BlogPost.objects.none()
    posts = BlogPost.objects.filter(status="published", is_enabled=True)
    return settings, posts


def get_public_blog_post(post_slug: str) -> tuple[BlogSettings, BlogPost | None]:
    settings, posts = get_public_blog_posts()
    if not settings.enable_blog:
        return settings, None
    try:
        return settings, posts.get(slug=post_slug)
    except BlogPost.DoesNotExist:
        return settings, None


def get_help_center_page() -> CustomPage:
    return get_or_create_managed_page("help_center")


def get_public_help_center_payload():
    page = get_help_center_page()
    if not page.is_enabled or page.status != "published":
        return None, FAQEntry.objects.none()
    faqs = FAQEntry.objects.filter(is_enabled=True)
    return page, faqs


def get_public_faq_entry(faq_slug: str) -> FAQEntry | None:
    page, _faqs = get_public_help_center_payload()
    if page is None:
        return None
    try:
        return FAQEntry.objects.get(slug=faq_slug, is_enabled=True)
    except FAQEntry.DoesNotExist:
        return None
