from django.shortcuts import get_object_or_404

from public.category.models import Tag
from public.storefront.services import (
    annotate_product_pricing,
    build_breadcrumbs,
    build_catalog_page,
    get_product_queryset,
    is_ajax_request,
    render_info_page,
    render_storefront,
)


def _search_queryset():
    return annotate_product_pricing(get_product_queryset())


def _render_search_response(request, context, page_title):
    template_name = "catalog/_listing_results.html" if is_ajax_request(request) else "catalog/listing.html"
    return render_storefront(request, template_name, context, page_title=page_title)


def search_results_view(request):
    query = request.GET.get("q", "").strip()
    description = f"Search results for '{query}'." if query else "Search across the storefront catalog."
    context = build_catalog_page(
        request,
        queryset=_search_queryset(),
        page_title="Search",
        page_description=description,
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Search", "")),
        extra_context={"search_query": query},
    )
    return _render_search_response(request, context, "Search")


def advanced_search_view(request):
    context = build_catalog_page(
        request,
        queryset=_search_queryset(),
        page_title="Advanced Search",
        page_description="Refine products by keyword, category, brand, and price range.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Advanced Search", "")),
        extra_context={"advanced_search": True},
    )
    return _render_search_response(request, context, "Advanced Search")


def visual_search_view(request):
    return render_info_page(
        request,
        title="Visual Search",
        body="Visual search has a storefront shell in place but still needs a backing image-recognition service before it can be enabled.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Visual Search", ""))},
    )


def tag_browse_view(request, tag_slug):
    tag = get_object_or_404(Tag, slug=tag_slug, is_active=True)
    context = build_catalog_page(
        request,
        queryset=_search_queryset().filter(tags=tag),
        page_title=tag.meta_title or tag.name,
        page_description=tag.meta_description or tag.description or f"Products tagged with {tag.name}.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Tags", "/search/"), (tag.name, "")),
        extra_context={"tag": tag},
    )
    return _render_search_response(request, context, tag.name)


def filtered_browse_view(request):
    context = build_catalog_page(
        request,
        queryset=_search_queryset(),
        page_title="Filtered Browse",
        page_description="Filtered storefront results using the active query-string criteria.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Filtered Browse", "")),
        extra_context={"filtered_browse": True},
    )
    return _render_search_response(request, context, "Filtered Browse")
