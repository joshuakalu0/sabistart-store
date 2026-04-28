import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils.html import strip_tags

from dashboard.store_settings.content_services import (
    get_public_faq_entry,
    get_public_help_center_payload,
    get_public_managed_page,
)
from public.storefront.forms import ContactForm
from public.storefront.services import build_breadcrumbs, render_info_page, render_storefront

logger = logging.getLogger(__name__)


def _handle_contact_form(request, title, body):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        logger.info("Storefront support submission: %s", form.cleaned_data)
        messages.success(request, "Your message has been recorded.")
        return redirect(request.path)
    return render_info_page(
        request,
        title=title,
        body=body,
        form=form,
        form_action=request.path,
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), (title, ""))},
    )


def help_center_view(request):
    page, faqs = get_public_help_center_payload()
    if page is None:
        raise Http404("The help center is disabled.")
    return render_storefront(
        request,
        "support/faq_index.html",
        {
            "page": page,
            "faqs": list(faqs),
            "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Help", "")) if page.show_breadcrumbs else [],
        },
        page_title=page.meta_title or page.title,
        page_description=page.meta_description or page.excerpt or page.title,
    )


def faq_detail_view(request, faq_slug):
    page, faqs = get_public_help_center_payload()
    faq = get_public_faq_entry(faq_slug)
    if page is None or faq is None:
        raise Http404("This FAQ is not available.")
    related = [item for item in faqs.exclude(pk=faq.pk)[:6]]
    return render_storefront(
        request,
        "support/faq_detail.html",
        {
            "page": page,
            "faq": faq,
            "related_faqs": related,
            "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Help", "/help/"), (faq.question, "")) if page.show_breadcrumbs else [],
        },
        page_title=faq.question,
        page_description=strip_tags(faq.answer)[:160],
    )


def contact_us_view(request):
    return _handle_contact_form(
        request,
        "Contact Us",
        "Send a support or sales inquiry to the store team.",
    )


def submit_ticket_view(request):
    return _handle_contact_form(
        request,
        "Submit Ticket",
        "Capture a structured support request through the themed storefront form.",
    )


def ticket_status_view(request, ticket_id):
    return render_info_page(
        request,
        title="Ticket Status",
        body=f"Ticket tracking for {ticket_id} is staged as a shell until support persistence is added.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Support", "/help/"), ("Ticket Status", ""))},
    )


def delivery_info_view(request):
    page = get_public_managed_page("delivery_information")
    if page is None:
        raise Http404("Delivery information is disabled.")
    return render_storefront(
        request,
        "shared/content_page.html",
        {
            "page": page,
            "headline": page.title,
            "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Delivery Info", "")) if page.show_breadcrumbs else [],
        },
        page_title=page.meta_title or page.title,
        page_description=page.meta_description or page.excerpt or page.title,
    )


def returns_policy_view(request):
    page = get_public_managed_page("returns_policy")
    if page is None:
        raise Http404("Returns policy is disabled.")
    return render_storefront(
        request,
        "shared/content_page.html",
        {
            "page": page,
            "headline": page.title,
            "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Returns", "")) if page.show_breadcrumbs else [],
        },
        page_title=page.meta_title or page.title,
        page_description=page.meta_description or page.excerpt or page.title,
    )


def warranty_info_view(request):
    page = get_public_managed_page("warranty_information")
    if page is None:
        raise Http404("Warranty information is disabled.")
    return render_storefront(
        request,
        "shared/content_page.html",
        {
            "page": page,
            "headline": page.title,
            "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Warranty", "")) if page.show_breadcrumbs else [],
        },
        page_title=page.meta_title or page.title,
        page_description=page.meta_description or page.excerpt or page.title,
    )
