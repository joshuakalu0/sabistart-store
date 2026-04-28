from django.db.models import F, Q

from public.storefront.services import (
    annotate_product_pricing,
    build_breadcrumbs,
    get_active_discount_campaigns,
    get_active_flash_sale,
    get_banner_slides,
    get_featured_brands,
    get_homepage_layout_cached,
    get_listable_product_queryset,
    get_recently_viewed_products,
    get_related_product_cards,
    get_serialized_products,
    get_service_highlights,
    get_store_editorial_cards,
    serialize_flash_sale,
    get_top_categories,
    render_info_page,
    render_storefront,
)


def home_view(request):
    layout = get_homepage_layout_cached(request)
    queryset = annotate_product_pricing(get_listable_product_queryset())
    active_flash_sale = get_active_flash_sale(request)
    featured_categories = get_top_categories(request, limit=getattr(
        layout, "featured_categories_count", 8) if layout else 8)
    featured_brands = get_featured_brands(request, limit=6)
    discount_campaigns = get_active_discount_campaigns(request, limit=3)

    featured_products = get_serialized_products(
        queryset.filter(is_featured=True).order_by(
            "-sales_count", "-created_at"),
        request,
        limit=getattr(layout, "featured_products_count", 8) if layout else 8,
    )
    if not featured_products:
        featured_products = get_serialized_products(
            queryset.order_by("-sales_count", "-created_at"), request, limit=8)

    context = {
        "hero_slides": get_banner_slides(request),
        "featured_categories": featured_categories,
        "featured_products": featured_products,
        "new_arrivals": get_serialized_products(
            queryset.filter(is_new=True).order_by(
                "-published_at", "-created_at"),
            request,
            limit=getattr(layout, "new_arrivals_count", 8) if layout else 8,
        ),
        "best_sellers": get_serialized_products(
            queryset.filter(is_bestseller=True).order_by(
                "-sales_count", "-created_at"),
            request,
            limit=getattr(layout, "best_sellers_count", 8) if layout else 8,
        ),
        "sale_products": get_serialized_products(
            queryset.filter(Q(is_on_sale=True) | Q(compare_at_price__gt=F(
                "price"))).order_by("-published_at", "-created_at"),
            request,
            limit=getattr(layout, "sale_section_count", 8) if layout else 8,
        ),
        "merchandising_tabs": [
            {"slug": "featured", "label": "Featured",
                "products": featured_products},
            {
                "slug": "new",
                "label": "New",
                "products": get_serialized_products(
                    queryset.filter(is_new=True).order_by(
                        "-published_at", "-created_at"),
                    request,
                    limit=6,
                ),
            },
            {
                "slug": "best-sellers",
                "label": "Best Sellers",
                "products": get_serialized_products(
                    queryset.filter(is_bestseller=True).order_by(
                        "-sales_count", "-created_at"),
                    request,
                    limit=6,
                ),
            },
            {
                "slug": "deals",
                "label": "Deals",
                "products": get_serialized_products(
                    queryset.filter(Q(is_on_sale=True) | Q(compare_at_price__gt=F(
                        "price"))).order_by("-published_at", "-created_at"),
                    request,
                    limit=6,
                ),
            },
        ],
        "featured_brands": featured_brands,
        "active_flash_sale_payload": serialize_flash_sale(active_flash_sale),
        "discount_campaigns": discount_campaigns,
        "service_highlights": get_service_highlights(request),
        "recently_viewed_products": get_recently_viewed_products(request)[:6],
        "store_editorial_cards": get_store_editorial_cards(request),
        "browsing_spotlight": get_related_product_cards(queryset.first(), request, limit=4) if queryset.exists() else [],
    }
    return render_storefront(
        request,
        "home.html",
        context,
        page_title="Home",
        page_description="Discover featured collections, new arrivals, and the storefront's top-selling products.",
    )


def maintenance_view(request):
    return render_info_page(
        request,
        title="Maintenance",
        body="The storefront is temporarily unavailable while updates are being applied. Check back shortly.",
        extra_context={"breadcrumbs": build_breadcrumbs(
            ("Home", "/"), ("Maintenance", ""))},
    )


def coming_soon_view(request):
    return render_info_page(
        request,
        title="Coming Soon",
        body="This section is staged for launch and will be published once the tenant is ready.",
        extra_context={"breadcrumbs": build_breadcrumbs(
            ("Home", "/"), ("Coming Soon", ""))},
    )


def custom_404_view(request, exception=None):
    return render_info_page(
        request,
        title="Page Not Found",
        body="The page you requested could not be found in this storefront.",
        status=404,
        extra_context={"breadcrumbs": build_breadcrumbs(
            ("Home", "/"), ("Not Found", ""))},
    )


def custom_500_view(request):
    return render_info_page(
        request,
        title="Server Error",
        body="The storefront hit an unexpected error while loading this page.",
        status=500,
        extra_context={"breadcrumbs": build_breadcrumbs(
            ("Home", "/"), ("Server Error", ""))},
    )
