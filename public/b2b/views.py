import logging

from django.contrib import messages
from django.shortcuts import redirect

from public.storefront.forms import B2BLeadForm
from public.storefront.services import build_breadcrumbs, render_info_page

logger = logging.getLogger(__name__)


def _b2b_form_page(request, title, body):
    form = B2BLeadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        logger.info("B2B storefront submission: %s", form.cleaned_data)
        messages.success(request, "Your request has been recorded.")
        return redirect(request.path)
    return render_info_page(
        request,
        title=title,
        body=body,
        form=form,
        form_action=request.path,
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("B2B", "/b2b/apply/"), (title, ""))},
    )


def b2b_application_view(request):
    return _b2b_form_page(request, "B2B Application", "Apply for wholesale access or negotiated pricing.")


def b2b_portal_view(request):
    return render_info_page(
        request,
        title="B2B Portal",
        body="The B2B portal route is available as a tenant-themed shell pending deeper account segmentation.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("B2B Portal", ""))},
    )


def request_for_quote_view(request):
    return _b2b_form_page(request, "Request for Quote", "Submit a quote request for bulk or contract purchasing.")


def quote_detail_view(request, quote_id):
    return render_info_page(
        request,
        title="Quote Detail",
        body=f"Quote detail for {quote_id} is currently exposed as a themed shell.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("B2B", "/b2b/apply/"), ("Quote Detail", ""))},
    )


def po_checkout_view(request):
    return render_info_page(
        request,
        title="PO Checkout",
        body="Purchase-order checkout is represented as a themed shell until B2B payment terms are added.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("PO Checkout", ""))},
    )


def contract_pricing_view(request):
    return render_info_page(
        request,
        title="Contract Pricing",
        body="Contract pricing content is exposed here without introducing new persistence models in this pass.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Contract Pricing", ""))},
    )


def company_management_view(request):
    return render_info_page(
        request,
        title="Company Management",
        body="Company-management tooling is presented as a tenant-themed shell.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Company Management", ""))},
    )


def invoice_history_view(request):
    return render_info_page(
        request,
        title="Invoice History",
        body="Invoice history is reserved for a later B2B accounting phase.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Invoices", ""))},
    )


def tax_exemption_view(request):
    return render_info_page(
        request,
        title="Tax Exemption",
        body="Tax-exemption workflows are represented as a storefront shell until tax-document handling is implemented.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Tax Exemption", ""))},
    )
