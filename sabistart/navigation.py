from __future__ import annotations

from django.urls import NoReverseMatch, reverse


PLATFORM_NAVIGATION = (
    {
        "title": "Platform",
        "items": (
            {"key": "platform_dashboard", "name": "Dashboard", "icon": "dashboard", "route": "platform:dashboard"},
            {"key": "platform_stores", "name": "Stores", "icon": "storefront", "route": "platform:stores"},
            {"key": "platform_users", "name": "Users", "icon": "group", "route": "platform:users"},
            {"key": "platform_provisioning", "name": "Provisioning Logs", "icon": "terminal", "route": "platform:provisioning_logs"},
            {"key": "platform_themes", "name": "Themes", "icon": "palette", "route": "platform_themes:home"},
            {"key": "platform_features", "name": "Feature Marketplace", "icon": "store", "route": "platform_features:home"},
            {"key": "platform_payments", "name": "Payments", "icon": "payments", "route": "platform_payments:home"},
            {"key": "platform_domains", "name": "Domains", "icon": "language", "route": "platform_domains:home"},
            {"key": "platform_diagnostics", "name": "Diagnostics", "icon": "monitor_heart", "route": "platform:diagnostics"},
        ),
    },
)


TENANT_NAVIGATION = (
    {
        "title": "Overview",
        "items": (
            {
                "key": "dashboard",
                "name": "Dashboard",
                "icon": "dashboard",
                "route": "dashboard:dashboard_home:home",
                "active_keys": ("dashboard", "home"),
            },
        ),
    },
    {
        "title": "Commerce",
        "items": (
            {
                "key": "pos",
                "name": "Point of Sale",
                "icon": "point_of_sale",
                "route": "dashboard:pos:dashboard",
                "feature_code": "max_pos_locations",
                "active_keys": ("pos", "pos_dashboard", "pos_register", "pos_sales", "pos_inventory", "pos_products", "pos_discounts"),
                "children": (
                    {"key": "pos_dashboard", "name": "POS Dashboard", "icon": "dashboard", "route": "dashboard:pos:dashboard", "feature_code": "max_pos_locations"},
                    {"key": "pos_register", "name": "Register", "icon": "point_of_sale", "route": "dashboard:pos:register", "feature_code": "max_pos_locations"},
                    {"key": "pos_sales", "name": "Sales", "icon": "receipt_long", "route": "dashboard:pos:sales", "feature_code": "max_pos_locations"},
                    {"key": "pos_inventory", "name": "Inventory", "icon": "inventory_2", "route": "dashboard:pos:inventory", "feature_code": "max_pos_locations"},
                    {"key": "pos_products", "name": "Products", "icon": "sell", "route": "dashboard:pos:products", "feature_code": "max_pos_locations"},
                    {"key": "pos_discounts", "name": "Discounts", "icon": "local_offer", "route": "dashboard:pos:discounts", "feature_code": "max_pos_locations"},
                ),
            },
            {
                "key": "products",
                "name": "Catalog",
                "icon": "inventory_2",
                "route": "dashboard:product_settings:product_list",
                "active_keys": ("products", "attributes", "attribute_groups", "categories", "brands", "tags"),
                "children": (
                    {"key": "products", "name": "Products", "icon": "inventory_2", "route": "dashboard:product_settings:product_list"},
                    {"key": "attribute_groups", "name": "Attribute Groups", "icon": "view_module", "route": "dashboard:product_settings:attribute_group_list"},
                    {"key": "attributes", "name": "Attributes", "icon": "tune", "route": "dashboard:product_settings:attribute_list"},
                    {"key": "categories", "name": "Categories", "icon": "category", "route": "dashboard:dashboard_categories:list"},
                    {"key": "brands", "name": "Brands", "icon": "storefront", "route": "dashboard:dashboard_categories:brand_list"},
                    {"key": "tags", "name": "Tags", "icon": "local_offer", "route": "dashboard:dashboard_categories:tag_list"},
                ),
            },
            {
                "key": "pricing",
                "name": "Pricing & Promotions",
                "icon": "sell",
                "route": "dashboard:pricing:currency_list",
                "active_keys": (
                    "pricing_currency",
                    "pricing_exchange",
                    "pricing_price_lists",
                    "pricing_discounts",
                    "pricing_auto_discounts",
                    "pricing_promotions",
                    "pricing_volume",
                    "pricing_flash",
                    "pricing_tax",
                ),
                "children": (
                    {"key": "pricing_currency", "name": "Currencies", "icon": "currency_exchange", "route": "dashboard:pricing:currency_list"},
                    {"key": "pricing_exchange", "name": "Exchange Rates", "icon": "swap_horiz", "route": "dashboard:pricing:exchange_rate_list"},
                    {"key": "pricing_price_lists", "name": "Price Lists", "icon": "price_change", "route": "dashboard:pricing:price_list_list"},
                    {"key": "pricing_discounts", "name": "Discount Codes", "icon": "local_offer", "route": "dashboard:pricing:discount_code_list", "feature_code": "discount_codes"},
                    {"key": "pricing_auto_discounts", "name": "Automatic Discounts", "icon": "auto_awesome", "route": "dashboard:pricing:automatic_discount_list"},
                    {"key": "pricing_promotions", "name": "Buy X Get Y", "icon": "redeem", "route": "dashboard:pricing:bxgy_list"},
                    {"key": "pricing_volume", "name": "Volume Tiers", "icon": "stacked_bar_chart", "route": "dashboard:pricing:volume_tier_list"},
                    {"key": "pricing_flash", "name": "Flash Sales", "icon": "bolt", "route": "dashboard:pricing:flash_sale_list"},
                    {"key": "pricing_tax", "name": "Tax Engine", "icon": "receipt_long", "route": "dashboard:pricing:tax_category_list"},
                ),
            },
        ),
    },
    {
        "title": "Growth",
        "items": (
            {
                "key": "analytics",
                "name": "Business Analytics",
                "icon": "analytics",
                "route": "dashboard:analytics:overview",
                "feature_code": "advanced_analytics",
                "active_keys": (
                    "analytics",
                    "analytics_overview",
                    "analytics_orders",
                    "analytics_products",
                    "analytics_inventory",
                    "analytics_customers",
                ),
                "children": (
                    {"key": "analytics_overview", "name": "Overview", "icon": "dashboard", "route": "dashboard:analytics:overview", "feature_code": "advanced_analytics"},
                    {"key": "analytics_orders", "name": "Orders", "icon": "receipt_long", "route": "dashboard:analytics:orders", "feature_code": "advanced_analytics"},
                    {"key": "analytics_products", "name": "Products", "icon": "sell", "route": "dashboard:analytics:products", "feature_code": "advanced_analytics"},
                    {"key": "analytics_inventory", "name": "Inventory", "icon": "inventory", "route": "dashboard:analytics:inventory", "feature_code": "advanced_analytics"},
                    {"key": "analytics_customers", "name": "Customers", "icon": "groups", "route": "dashboard:analytics:customers", "feature_code": "advanced_analytics"},
                ),
            },
            {
                "key": "payments",
                "name": "Payments",
                "icon": "payments",
                "route": "dashboard:payments_tenant:tenant_home",
                "active_keys": (
                    "payments",
                    "payments_overview",
                    "payments_transactions",
                    "payments_gateways",
                    "payments_balance",
                    "payments_refunds",
                    "payments_disputes",
                    "payments_fraud",
                    "payments_analytics",
                    "payments_settings",
                ),
                "children": (
                    {"key": "payments_overview", "name": "Overview", "icon": "dashboard", "route": "dashboard:payments_tenant:tenant_home"},
                    {"key": "payments_transactions", "name": "Transactions", "icon": "receipt_long", "route": "dashboard:payments_tenant:transaction_list"},
                    {"key": "payments_gateways", "name": "Gateways", "icon": "hub", "route": "dashboard:payments_tenant:gateway_mode_list"},
                    {"key": "payments_balance", "name": "Balance & Payouts", "icon": "account_balance_wallet", "route": "dashboard:payments_tenant:balance_list"},
                    {"key": "payments_refunds", "name": "Refunds", "icon": "assignment_return", "route": "dashboard:payments_tenant:refund_list"},
                    {"key": "payments_disputes", "name": "Disputes", "icon": "gavel", "route": "dashboard:payments_tenant:dispute_list"},
                    {"key": "payments_fraud", "name": "Fraud & Risk", "icon": "security", "route": "dashboard:payments_tenant:fraud_assessment_list"},
                    {"key": "payments_analytics", "name": "Analytics", "icon": "analytics", "route": "dashboard:payments_tenant:analytics", "feature_code": "advanced_analytics"},
                    {"key": "payments_settings", "name": "Settings", "icon": "settings", "route": "dashboard:payments_tenant:profile_edit"},
                ),
            },
            {
                "key": "marketplace",
                "name": "Marketplace",
                "icon": "store",
                "route": "dashboard:feature_marketplace:home",
                "active_keys": ("marketplace", "marketplace_overview", "marketplace_catalog", "marketplace_purchases", "marketplace_entitlements", "marketplace_usage"),
                "children": (
                    {"key": "marketplace_overview", "name": "Overview", "icon": "dashboard", "route": "dashboard:feature_marketplace:home"},
                    {"key": "marketplace_catalog", "name": "Catalog", "icon": "apps", "route": "dashboard:feature_marketplace:catalog"},
                    {"key": "marketplace_purchases", "name": "Purchases", "icon": "receipt_long", "route": "dashboard:feature_marketplace:purchases"},
                    {"key": "marketplace_entitlements", "name": "Entitlements", "icon": "verified", "route": "dashboard:feature_marketplace:entitlements"},
                    {"key": "marketplace_usage", "name": "Usage & Quotas", "icon": "speed", "route": "dashboard:feature_marketplace:usage"},
                ),
            },
            {
                "key": "monitoring",
                "name": "Traffic Analytics",
                "icon": "query_stats",
                "route": "dashboard:monitoring:overview",
                "feature_code": "advanced_analytics",
                "active_keys": ("monitoring", "monitoring_overview", "monitoring_pages", "monitoring_sessions"),
                "children": (
                    {"key": "monitoring_overview", "name": "Overview", "icon": "dashboard", "route": "dashboard:monitoring:overview", "feature_code": "advanced_analytics"},
                    {"key": "monitoring_pages", "name": "Pages", "icon": "description", "route": "dashboard:monitoring:pages", "feature_code": "advanced_analytics"},
                    {"key": "monitoring_sessions", "name": "Sessions", "icon": "groups", "route": "dashboard:monitoring:sessions", "feature_code": "advanced_analytics"},
                ),
            },
            {
                "key": "notifications",
                "name": "Notifications",
                "icon": "notifications",
                "route": "dashboard:notification_dashboard_index",
                "active_keys": ("notifications",),
                "children": (
                    {"key": "notifications", "name": "Dashboard", "icon": "dashboard", "route": "dashboard:notification_dashboard_index"},
                    {"key": "notification_channels", "name": "Channels", "icon": "hub", "route": "dashboard:notification_channel_list"},
                    {"key": "notification_templates", "name": "Templates", "icon": "edit_document", "route": "dashboard:notification_template_list"},
                    {"key": "notification_logs", "name": "Delivery Logs", "icon": "history", "route": "dashboard:notification_log_list"},
                    {"key": "notification_preferences", "name": "Preferences", "icon": "tune", "route": "dashboard:notification_preference_list"},
                    {"key": "notification_webhooks", "name": "Webhooks", "icon": "webhook", "route": "dashboard:notification_webhook_list", "feature_code": "webhooks"},
                ),
            },
        ),
    },
    {
        "title": "Store Operations",
        "items": (
            {
                "key": "domains",
                "name": "Domains & SSL",
                "icon": "language",
                "route": "dashboard:domain:list",
                "active_keys": (
                    "domains",
                    "domains_list",
                    "domains_search",
                    "domains_portfolio",
                    "domains_orders",
                    "domains_contacts",
                    "domains_notifications",
                ),
                "children": (
                    {"key": "domains_list", "name": "Overview", "icon": "dashboard", "route": "dashboard:domain:list"},
                    {"key": "domains_search", "name": "Discover & Buy", "icon": "travel_explore", "route": "dashboard:domain:checkout"},
                    {"key": "domains_portfolio", "name": "Portfolio", "icon": "domain", "route": "dashboard:domain:portfolio"},
                    {"key": "domains_orders", "name": "Orders & Renewals", "icon": "receipt_long", "route": "dashboard:domain:orders"},
                    {"key": "domains_contacts", "name": "Contacts", "icon": "contacts", "route": "dashboard:domain:contacts"},
                    {"key": "domains_notifications", "name": "Notifications", "icon": "notifications", "route": "dashboard:domain:notifications"},
                ),
            },
            {
                "key": "settings",
                "name": "Storefront & Settings",
                "icon": "tune",
                "route": "dashboard:store_settings:manage_store_settings",
                "active_keys": (
                    "settings",
                    "store_theme",
                    "store_theme_marketplace",
                    "store_theme_installed",
                    "store_settings",
                    "store_social",
                    "store_product_page",
                    "store_content_overview",
                    "store_content_pages",
                    "store_content_blog",
                    "store_content_faq",
                    "store_content_custom_pages",
                ),
                "children": (
                    {"key": "store_theme", "name": "Theme Settings", "icon": "palette", "route": "dashboard:store_settings:manage_theme_settings"},
                    {"key": "store_theme_marketplace", "name": "Theme Marketplace", "icon": "palette", "route": "dashboard:themes:marketplace"},
                    {"key": "store_theme_installed", "name": "Installed Themes", "icon": "widgets", "route": "dashboard:themes:installed"},
                    {"key": "store_settings", "name": "Store Settings", "icon": "storefront", "route": "dashboard:store_settings:manage_store_settings"},
                    {"key": "store_social", "name": "Social Links", "icon": "share", "route": "dashboard:store_settings:manage_social_media_links"},
                    {"key": "store_product_page", "name": "Product Page", "icon": "web", "route": "dashboard:store_settings:manage_product_page_settings"},
                    {"key": "store_content_overview", "name": "Content Center", "icon": "article", "route": "dashboard:content_manager:overview"},
                    {"key": "store_content_pages", "name": "Policies & Info", "icon": "description", "route": "dashboard:content_manager:managed_pages"},
                    {"key": "store_content_blog", "name": "Blog Posts", "icon": "feed", "route": "dashboard:content_manager:blog_posts"},
                    {"key": "store_content_faq", "name": "FAQs", "icon": "quiz", "route": "dashboard:content_manager:faqs"},
                    {"key": "store_content_custom_pages", "name": "Custom Pages", "icon": "web_stories", "route": "dashboard:content_manager:custom_pages"},
                ),
            },
        ),
    },
    {
        "title": "People",
        "items": (
            {
                "key": "users",
                "name": "Users & Staff",
                "icon": "group",
                "route": "dashboard:user_settings:user_list",
                "active_keys": ("users", "staff", "roles", "customers", "audit"),
                "children": (
                    {"key": "users", "name": "Users", "icon": "manage_accounts", "route": "dashboard:user_settings:user_list"},
                    {"key": "staff", "name": "Store Staff", "icon": "badge", "route": "dashboard:user_settings:staff_list"},
                    {"key": "roles", "name": "Roles & Permissions", "icon": "security", "route": "dashboard:user_settings:role_list"},
                    {"key": "customers", "name": "Customers", "icon": "people", "route": "dashboard:user_settings:customer_list"},
                    {"key": "audit", "name": "Audit Logs", "icon": "policy", "route": "dashboard:user_settings:login_audit_list"},
                ),
            },
        ),
    },
)


def _reverse_or_none(route_name: str, *, prefix: str | None = None) -> str | None:
    kwargs = {"prefix": prefix} if prefix else {}
    try:
        return reverse(route_name, kwargs=kwargs)
    except NoReverseMatch:
        return None


def build_platform_navigation(active_key: str | None = None):
    sections = []
    for section in PLATFORM_NAVIGATION:
        items = []
        for item in section["items"]:
            url = _reverse_or_none(item["route"])
            if not url:
                continue
            items.append(
                {
                    "key": item["key"],
                    "name": item["name"],
                    "icon": item["icon"],
                    "url": url,
                    "active": item["key"] == active_key,
                }
            )
        if items:
            sections.append({"title": section["title"], "items": items})
    return sections


def iter_tenant_navigation(prefix: str):
    for section in TENANT_NAVIGATION:
        built_items = []
        for item in section["items"]:
            url = _reverse_or_none(item["route"], prefix=prefix)
            if not url:
                continue
            children = []
            for child in item.get("children", ()):
                child_url = _reverse_or_none(child["route"], prefix=prefix)
                if not child_url:
                    continue
                children.append({**child, "url": child_url})
            built_items.append({**item, "url": url, "children": children})
        if built_items:
            yield {"title": section["title"], "items": built_items}
