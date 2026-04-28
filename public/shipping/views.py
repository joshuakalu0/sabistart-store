from public.storefront.services import build_breadcrumbs, render_info_page


def store_locator_view(request):
    return render_info_page(
        request,
        title="Store Locator",
        body="Physical store discovery is available as a themed shell until tenant location data is connected.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Store Locator", ""))},
    )


def store_detail_view(request, store_slug):
    return render_info_page(
        request,
        title=store_slug.replace("-", " ").title(),
        body="Store detail content can be connected later without changing this route.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Store Locator", "/stores/"), (store_slug, ""))},
    )


def click_collect_info_view(request, store_slug):
    return render_info_page(
        request,
        title="Click & Collect",
        body=f"Click and collect information for {store_slug} is represented as a themed shell.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Store Locator", "/stores/"), ("Click & Collect", ""))},
    )


def shipping_info_view(request):
    return render_info_page(
        request,
        title="Shipping Information",
        body="General shipping content is rendered through the tenant theme and can be extended with carrier-specific logic later.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Shipping Info", ""))},
    )
