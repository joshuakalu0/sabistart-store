"""
store_utils — Public API
========================
Import from here in views, templates, middleware, and tasks.

Storefront (user-facing):
    from store_utils import (
        get_store_settings, get_theme_settings,
        format_price, get_theme_css_variables,
        cart_add, cart_totals, cart_count,
        wishlist_toggle, wishlist_count,
        store_context,               # Django context processor
        maintenance_mode_middleware, # WSGI middleware factory
        build_breadcrumbs,
        get_homepage_sections,
        get_header_context, get_footer_context,
        get_email_branding_context,
        get_product_badge, get_image_ratio_css,
    )

Dashboard / analytics:
    from store_utils import (
        get_dashboard_home_data,
        get_store_health,
        get_revenue_summary, get_revenue_over_time,
        get_order_status_breakdown,
        get_top_selling_products, get_low_stock_products,
        get_customer_summary, get_customer_ltv,
        get_inventory_health_summary,
        get_product_analytics_page,
        get_customer_analytics_page,
        get_order_analytics_page,
        generate_dashboard_alerts,
        parse_period,
        export_orders_csv, export_products_csv, export_customers_csv,
        revenue_chart_data, order_status_chart_data,
    )
"""

# ── Storefront utils ───────────────────────────────────────────────────────
from .storefront_utils import (
    # Cache helpers
    cache_key,
    invalidate_settings_cache,

    # Settings accessors
    get_store_settings,
    get_theme_settings,
    get_header_settings,
    get_footer_settings,
    get_homepage_layout,
    get_product_display_settings,
    get_product_page_settings,
    get_cart_settings,
    get_checkout_settings,
    get_search_settings,
    get_email_template_settings,
    get_social_links,
    get_notification_settings,
    get_mobile_app_settings,
    get_blog_settings,
    get_popup_settings,
    get_performance_settings,

    # Theme / CSS
    get_theme_css_variables,
    get_google_fonts_url,
    get_theme_meta,

    # Navigation
    get_navigation_menu,
    build_menu_tree,
    build_breadcrumbs,

    # Currency / price
    format_price,
    calculate_tax,
    calculate_discount,
    format_price_range,

    # Homepage
    get_homepage_sections,

    # Header / Footer
    get_header_context,
    get_footer_context,

    # Search
    build_search_config,
    tokenize_query,
    build_search_queryset,

    # Product display
    get_product_badge,
    get_image_ratio_css,
    get_hover_effect_class,
    get_products_per_row_classes,

    # Cart
    cart_add,
    cart_remove,
    cart_update_qty,
    cart_clear,
    cart_count,
    cart_totals,
    cart_apply_coupon,

    # Wishlist
    wishlist_get,
    wishlist_add,
    wishlist_remove,
    wishlist_toggle,
    wishlist_count,
    wishlist_contains,

    # Popup
    should_show_popup,
    dismiss_popup,

    # SEO
    get_store_meta_tags,
    get_organization_jsonld,
    get_product_jsonld,

    # Email
    get_email_branding_context,

    # PWA
    generate_pwa_manifest,

    # Maintenance
    is_maintenance_mode,
    maintenance_mode_middleware,

    # Context processor
    store_context,
)

# ── Dashboard / analytics utils ───────────────────────────────────────────
from .dashboard_analytics_utils import (
    # Date ranges
    DateRange,
    parse_period,
    today_range,
    yesterday_range,
    last_n_days,
    this_month_range,
    last_month_range,
    this_year_range,
    custom_range,

    # Revenue
    get_revenue_summary,
    get_revenue_over_time,
    get_revenue_by_category,

    # Orders
    get_order_status_breakdown,
    get_average_fulfillment_time,
    get_order_geography,
    get_hourly_order_heatmap,

    # Products
    get_top_selling_products,
    get_low_stock_products,
    get_out_of_stock_products,
    get_product_conversion_rate,
    get_dead_stock_products,

    # Customers
    get_customer_summary,
    get_customer_ltv,
    get_new_customers_over_time,
    get_customer_cohort_retention,

    # Inventory
    get_inventory_health_summary,
    get_stock_turnover_rate,

    # Marketing
    get_coupon_usage_summary,
    get_abandoned_cart_stats,

    # Store health
    get_store_health,

    # Comparison
    pct_change,
    build_kpi_card,

    # Chart serializers
    to_line_chart_data,
    to_bar_chart_data,
    to_doughnut_chart_data,
    revenue_chart_data,
    order_status_chart_data,
    category_revenue_chart_data,

    # Exports
    export_orders_csv,
    export_products_csv,
    export_customers_csv,

    # Alerts
    generate_dashboard_alerts,

    # Aggregators
    get_dashboard_home_data,
    get_analytics_overview,
    get_product_analytics_page,
    get_customer_analytics_page,
    get_order_analytics_page,
)

__all__ = [
    # storefront
    "cache_key", "invalidate_settings_cache",
    "get_store_settings", "get_theme_settings", "get_header_settings",
    "get_footer_settings", "get_homepage_layout", "get_product_display_settings",
    "get_product_page_settings", "get_cart_settings", "get_checkout_settings",
    "get_search_settings", "get_email_template_settings", "get_social_links",
    "get_notification_settings", "get_mobile_app_settings", "get_blog_settings",
    "get_popup_settings", "get_performance_settings",
    "get_theme_css_variables", "get_google_fonts_url", "get_theme_meta",
    "get_navigation_menu", "build_menu_tree", "build_breadcrumbs",
    "format_price", "calculate_tax", "calculate_discount", "format_price_range",
    "get_homepage_sections", "get_header_context", "get_footer_context",
    "build_search_config", "tokenize_query", "build_search_queryset",
    "get_product_badge", "get_image_ratio_css", "get_hover_effect_class",
    "get_products_per_row_classes",
    "cart_add", "cart_remove", "cart_update_qty", "cart_clear", "cart_count",
    "cart_totals", "cart_apply_coupon",
    "wishlist_get", "wishlist_add", "wishlist_remove", "wishlist_toggle",
    "wishlist_count", "wishlist_contains",
    "should_show_popup", "dismiss_popup",
    "get_store_meta_tags", "get_organization_jsonld", "get_product_jsonld",
    "get_email_branding_context", "generate_pwa_manifest",
    "is_maintenance_mode", "maintenance_mode_middleware", "store_context",
    # analytics
    "DateRange", "parse_period", "today_range", "yesterday_range",
    "last_n_days", "this_month_range", "last_month_range", "this_year_range",
    "custom_range",
    "get_revenue_summary", "get_revenue_over_time", "get_revenue_by_category",
    "get_order_status_breakdown", "get_average_fulfillment_time",
    "get_order_geography", "get_hourly_order_heatmap",
    "get_top_selling_products", "get_low_stock_products", "get_out_of_stock_products",
    "get_product_conversion_rate", "get_dead_stock_products",
    "get_customer_summary", "get_customer_ltv", "get_new_customers_over_time",
    "get_customer_cohort_retention",
    "get_inventory_health_summary", "get_stock_turnover_rate",
    "get_coupon_usage_summary", "get_abandoned_cart_stats",
    "get_store_health", "pct_change", "build_kpi_card",
    "to_line_chart_data", "to_bar_chart_data", "to_doughnut_chart_data",
    "revenue_chart_data", "order_status_chart_data", "category_revenue_chart_data",
    "export_orders_csv", "export_products_csv", "export_customers_csv",
    "generate_dashboard_alerts",
    "get_dashboard_home_data", "get_analytics_overview",
    "get_product_analytics_page", "get_customer_analytics_page",
    "get_order_analytics_page",
]
