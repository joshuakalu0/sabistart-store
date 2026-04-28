from django.db.models import Q
from django.shortcuts import get_object_or_404

from public.category.models import Brand, Category, Tag
from public.storefront.services import (
    annotate_product_pricing,
    build_breadcrumbs,
    build_catalog_page,
    get_active_flash_sale,
    get_listable_product_queryset,
    is_ajax_request,
    render_storefront,
)


def _catalog_base_queryset():
    return annotate_product_pricing(get_listable_product_queryset())


def _render_catalog_response(request, context, page_title):
    template_name = "catalog/_listing_results.html" if is_ajax_request(request) else "catalog/listing.html"
    return render_storefront(request, template_name, context, page_title=page_title)


def shop_all_view(request):
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset(),
        page_title="Shop All",
        page_description="Browse the full tenant catalog with filtering, sorting, and pagination.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Shop All", "")),
    )
    return _render_catalog_response(request, context, "Shop All")


def category_detail_view(request, category_slug):
    category = get_object_or_404(Category, slug=category_slug, is_active=True, is_visible=True)
    queryset = _catalog_base_queryset().filter(categories=category)
    child_categories = list(category.children.filter(is_active=True, is_visible=True).order_by("display_order", "name"))
    context = build_catalog_page(
        request,
        queryset=queryset,
        page_title=category.meta_title or category.name,
        page_description=category.meta_description or category.description or f"Browse {category.name} products.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Shop All", "/shop/"), (category.name, "")),
        extra_context={"category": category, "child_categories": child_categories},
    )
    return _render_catalog_response(request, context, category.name)


def subcategory_detail_view(request, category_slug, subcategory_slug):
    parent = get_object_or_404(Category, slug=category_slug, is_active=True, is_visible=True)
    subcategory = get_object_or_404(
        Category,
        slug=subcategory_slug,
        parent=parent,
        is_active=True,
        is_visible=True,
    )
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().filter(categories=subcategory),
        page_title=subcategory.meta_title or subcategory.name,
        page_description=subcategory.meta_description or subcategory.description or f"Browse {subcategory.name} products.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Shop All", "/shop/"), (parent.name, f"/c/{parent.slug}/"), (subcategory.name, "")),
        extra_context={"category": subcategory, "parent_category": parent},
    )
    return _render_catalog_response(request, context, subcategory.name)


def brands_directory_view(request):
    brands = Brand.objects.filter(is_active=True).order_by("-featured", "display_order", "name")
    context = {
        "page_title": "Brands",
        "page_description": "Browse all brands currently available in this storefront.",
        "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Brands", "")),
        "brands": brands,
    }
    return render_storefront(request, "catalog/brands.html", context, page_title="Brands")


def brand_detail_view(request, brand_slug):
    brand = get_object_or_404(Brand, slug=brand_slug, is_active=True)
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().filter(brand=brand),
        page_title=brand.meta_title or brand.name,
        page_description=brand.meta_description or brand.description or f"Browse products from {brand.name}.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Brands", "/brands/"), (brand.name, "")),
        extra_context={"brand": brand},
    )
    return _render_catalog_response(request, context, brand.name)


def collections_list_view(request):
    context = {
        "page_title": "Collections",
        "page_description": "Explore curated collections built from storefront tags and merchandising rules.",
        "breadcrumbs": build_breadcrumbs(("Home", "/"), ("Collections", "")),
        "collections": Tag.objects.filter(is_active=True).order_by("name"),
    }
    return render_storefront(request, "catalog/collections.html", context, page_title="Collections")


def collection_detail_view(request, collection_slug):
    collection = get_object_or_404(Tag, slug=collection_slug, is_active=True)
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().filter(tags=collection),
        page_title=collection.meta_title or collection.name,
        page_description=collection.meta_description or collection.description or f"Browse the {collection.name} collection.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Collections", "/collections/"), (collection.name, "")),
        extra_context={"collection": collection},
    )
    return _render_catalog_response(request, context, collection.name)


def new_arrivals_view(request):
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().filter(Q(is_new=True) | Q(published_at__isnull=False)).order_by("-published_at", "-created_at"),
        page_title="New Arrivals",
        page_description="Latest products added to this storefront.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("New Arrivals", "")),
    )
    return _render_catalog_response(request, context, "New Arrivals")


def best_sellers_view(request):
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().filter(Q(is_bestseller=True) | Q(sales_count__gt=0)).order_by("-sales_count", "-created_at"),
        page_title="Best Sellers",
        page_description="Top-performing products across the storefront.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Best Sellers", "")),
    )
    return _render_catalog_response(request, context, "Best Sellers")


def trending_view(request):
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().order_by("-view_count", "-sales_count", "-created_at"),
        page_title="Trending",
        page_description="Products with the strongest current momentum.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Trending", "")),
    )
    return _render_catalog_response(request, context, "Trending")


def deals_view(request):
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().filter(Q(is_on_sale=True) | Q(compare_at_price__gt=0)).order_by("-published_at", "-created_at"),
        page_title="Deals",
        page_description="Discounted products and sale-driven merchandise.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Deals", "")),
    )
    return _render_catalog_response(request, context, "Deals")


def flash_sale_view(request):
    flash_sale = get_active_flash_sale(request)
    queryset = _catalog_base_queryset().none()
    description = "There is no active flash sale right now."

    if flash_sale:
        description = flash_sale.description or "Limited-time pricing on highlighted products."
        if flash_sale.applies_to_all_products:
            queryset = _catalog_base_queryset()
        else:
            product_ids = [item.product_id for item in flash_sale.items.all() if item.product_id]
            queryset = _catalog_base_queryset().filter(id__in=product_ids)

    context = build_catalog_page(
        request,
        queryset=queryset,
        page_title="Flash Sale",
        page_description=description,
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Flash Sale", "")),
        extra_context={"flash_sale": flash_sale},
    )
    return _render_catalog_response(request, context, "Flash Sale")


def clearance_view(request):
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().filter(is_on_sale=True).order_by("effective_price", "-created_at"),
        page_title="Clearance",
        page_description="Marked-down inventory prioritized by lowest current price.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Clearance", "")),
    )
    return _render_catalog_response(request, context, "Clearance")


def gift_guide_view(request):
    context = build_catalog_page(
        request,
        queryset=_catalog_base_queryset().filter(Q(is_featured=True) | Q(is_bestseller=True)).order_by("-sales_count", "-created_at"),
        page_title="Gift Guide",
        page_description="Curated product picks for gifting and seasonal buying.",
        breadcrumbs=build_breadcrumbs(("Home", "/"), ("Gift Guide", "")),
    )
    return _render_catalog_response(request, context, "Gift Guide")
