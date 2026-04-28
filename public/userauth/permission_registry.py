from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class PermissionDefinition:
    codename: str
    name: str
    description: str

    @property
    def category(self) -> str:
        return self.codename.split(".", 1)[0]


@dataclass(frozen=True)
class RoleDefinition:
    slug: str
    name: str
    description: str
    color: str
    sort_order: int
    permission_codenames: tuple[str, ...] | str


PERMISSION_CATEGORY_LABELS = {
    "dashboard": "Dashboard",
    "products": "Products",
    "attribute_groups": "Attribute Groups",
    "attributes": "Attributes",
    "categories": "Categories",
    "brands": "Brands",
    "tags": "Tags",
    "pricing": "Pricing & Promotions",
    "pos": "Point of Sale",
    "payments": "Payments",
    "marketplace": "Marketplace",
    "domains": "Domains & SSL",
    "notifications": "Notifications",
    "settings": "Storefront & Settings",
    "users": "Users",
    "staff": "Store Staff",
    "roles": "Roles & Permissions",
    "customers": "Customers",
    "audit": "Audit & Compliance",
}


PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    PermissionDefinition("dashboard.view", "View Dashboard", "Access the tenant dashboard home and overview surfaces."),
    PermissionDefinition("products.view", "View Products", "Browse and inspect the product catalog."),
    PermissionDefinition("products.create", "Create Products", "Create new products in the catalog."),
    PermissionDefinition("products.edit", "Edit Products", "Update existing products and product data."),
    PermissionDefinition("products.delete", "Delete Products", "Delete products from the catalog."),
    PermissionDefinition("products.publish", "Publish Products", "Publish, unpublish, or otherwise change product visibility."),
    PermissionDefinition("products.import", "Import Products", "Bulk import product data."),
    PermissionDefinition("attribute_groups.view", "View Attribute Groups", "View product attribute groups."),
    PermissionDefinition("attribute_groups.create", "Create Attribute Groups", "Create new attribute groups."),
    PermissionDefinition("attribute_groups.edit", "Edit Attribute Groups", "Update attribute group configuration."),
    PermissionDefinition("attribute_groups.delete", "Delete Attribute Groups", "Delete attribute groups."),
    PermissionDefinition("attributes.view", "View Attributes", "View product attributes and values."),
    PermissionDefinition("attributes.create", "Create Attributes", "Create product attributes."),
    PermissionDefinition("attributes.edit", "Edit Attributes", "Edit product attributes."),
    PermissionDefinition("attributes.delete", "Delete Attributes", "Delete product attributes."),
    PermissionDefinition("categories.view", "View Categories", "View store categories."),
    PermissionDefinition("categories.create", "Create Categories", "Create store categories."),
    PermissionDefinition("categories.edit", "Edit Categories", "Edit store categories."),
    PermissionDefinition("categories.delete", "Delete Categories", "Delete store categories."),
    PermissionDefinition("brands.view", "View Brands", "View store brands."),
    PermissionDefinition("brands.create", "Create Brands", "Create store brands."),
    PermissionDefinition("brands.edit", "Edit Brands", "Edit store brands."),
    PermissionDefinition("brands.delete", "Delete Brands", "Delete store brands."),
    PermissionDefinition("tags.view", "View Tags", "View product tags."),
    PermissionDefinition("tags.create", "Create Tags", "Create product tags."),
    PermissionDefinition("tags.edit", "Edit Tags", "Edit product tags."),
    PermissionDefinition("tags.delete", "Delete Tags", "Delete product tags."),
    PermissionDefinition("pricing.view", "View Pricing", "View currencies, rates, discounts, and tax settings."),
    PermissionDefinition("pricing.manage", "Manage Pricing", "Create and edit pricing, discount, and tax rules."),
    PermissionDefinition("pricing.export", "Export Pricing Data", "Export pricing and promotion data."),
    PermissionDefinition("pos.view", "View POS", "Access the POS dashboard and sales surfaces."),
    PermissionDefinition("pos.sell", "Process POS Sales", "Create and complete POS sales."),
    PermissionDefinition("pos.manage_inventory", "Manage POS Inventory", "Adjust POS inventory and stock levels."),
    PermissionDefinition("pos.manage_products", "Manage POS Products", "Create and edit POS products and store catalog entries."),
    PermissionDefinition("pos.view_reports", "View POS Reports", "View POS sales and inventory reports."),
    PermissionDefinition("payments.view", "View Payments", "View balances, transactions, and payment activity."),
    PermissionDefinition("payments.request_payout", "Request Payouts", "Submit payout requests."),
    PermissionDefinition("payments.manage_gateways", "Manage Payment Gateways", "Configure tenant payment gateway modes and credentials."),
    PermissionDefinition("payments.view_ledger", "View Payment Ledger", "Inspect balances, ledger history, and payout details."),
    PermissionDefinition("payments.manage_profile", "Manage Payment Profile", "Update tenant payment profile and settings."),
    PermissionDefinition("payments.issue_refund", "Issue Refunds", "Initiate or manage transaction refunds."),
    PermissionDefinition("payments.manage_disputes", "Manage Disputes", "View disputes and submit evidence."),
    PermissionDefinition("payments.view_analytics", "View Payment Analytics", "Access payment analytics and performance reports."),
    PermissionDefinition("marketplace.view", "View Marketplace", "Browse marketplace catalog, purchases, and entitlements."),
    PermissionDefinition("marketplace.purchase", "Purchase Features", "Purchase marketplace features, bundles, or credits."),
    PermissionDefinition("marketplace.manage_usage", "Manage Feature Usage", "View and manage entitlement usage and quotas."),
    PermissionDefinition("marketplace.view_purchases", "View Marketplace Purchases", "Review marketplace purchase history and status."),
    PermissionDefinition("domains.view", "View Domains", "View connected custom domains and SSL status."),
    PermissionDefinition("domains.add", "Add Domains", "Add and connect custom domains."),
    PermissionDefinition("domains.edit", "Edit Domains", "Update custom domain configuration."),
    PermissionDefinition("domains.delete", "Delete Domains", "Remove connected custom domains."),
    PermissionDefinition("domains.verify", "Verify Domains", "Retry or manage domain verification."),
    PermissionDefinition("notifications.view", "View Notifications", "Access notification dashboard and delivery information."),
    PermissionDefinition("notifications.manage_channels", "Manage Channels", "Configure notification channels."),
    PermissionDefinition("notifications.manage_templates", "Manage Templates", "Create and edit notification templates."),
    PermissionDefinition("notifications.view_logs", "View Notification Logs", "Inspect notification logs and delivery history."),
    PermissionDefinition("notifications.manage_preferences", "Manage Preferences", "Update notification preferences."),
    PermissionDefinition("notifications.manage_webhooks", "Manage Notification Webhooks", "Configure notification webhooks."),
    PermissionDefinition("settings.view", "View Settings", "Access store settings pages."),
    PermissionDefinition("settings.edit", "Edit Settings", "Update store settings and operational preferences."),
    PermissionDefinition("settings.theme", "Manage Theme", "Update theme and storefront presentation settings."),
    PermissionDefinition("settings.navigation", "Manage Navigation", "Update storefront menus and navigation."),
    PermissionDefinition("settings.seo", "Manage SEO", "Update SEO and discovery settings."),
    PermissionDefinition("settings.billing", "Manage Billing Settings", "Manage billing-facing tenant settings."),
    PermissionDefinition("users.view", "View Users", "View tenant users."),
    PermissionDefinition("users.create", "Create Users", "Create tenant users."),
    PermissionDefinition("users.edit", "Edit Users", "Edit tenant user accounts."),
    PermissionDefinition("users.deactivate", "Deactivate Users", "Deactivate or soft-delete tenant users."),
    PermissionDefinition("staff.view", "View Staff", "View staff memberships and assignments."),
    PermissionDefinition("staff.invite", "Invite Staff", "Add or invite new staff members."),
    PermissionDefinition("staff.edit", "Edit Staff", "Edit staff roles, access, and status."),
    PermissionDefinition("staff.remove", "Remove Staff", "Remove or deactivate staff members."),
    PermissionDefinition("roles.view", "View Roles", "View roles and permission matrices."),
    PermissionDefinition("roles.create", "Create Roles", "Create custom staff roles."),
    PermissionDefinition("roles.edit", "Edit Roles", "Update role definitions and permission sets."),
    PermissionDefinition("roles.delete", "Delete Roles", "Delete custom roles."),
    PermissionDefinition("customers.view", "View Customers", "View customer profiles and segments."),
    PermissionDefinition("customers.create", "Create Customers", "Create customer records."),
    PermissionDefinition("customers.edit", "Edit Customers", "Edit customer data and notes."),
    PermissionDefinition("customers.delete", "Delete Customers", "Delete or anonymize customer records."),
    PermissionDefinition("customers.export", "Export Customers", "Export customer data."),
    PermissionDefinition("audit.view", "View Audit Logs", "View login audit and staff activity logs."),
    PermissionDefinition("audit.export", "Export Audit Logs", "Export audit and compliance data."),
)


ALL_PERMISSION_CODENAMES = tuple(definition.codename for definition in PERMISSION_DEFINITIONS)
PERMISSION_CODENAMES = tuple((definition.codename, definition.name) for definition in PERMISSION_DEFINITIONS)
PERMISSION_CATEGORY_CHOICES = tuple(
    (key, label) for key, label in PERMISSION_CATEGORY_LABELS.items()
)


def permissions_for_prefixes(*prefixes: str, exclude: set[str] | None = None) -> tuple[str, ...]:
    exclude = exclude or set()
    wanted = set(prefixes)
    return tuple(
        definition.codename
        for definition in PERMISSION_DEFINITIONS
        if definition.category in wanted and definition.codename not in exclude
    )


BUILT_IN_ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        slug="owner",
        name="Owner",
        description="Full access to every live tenant dashboard capability.",
        color="#0f172a",
        sort_order=1,
        permission_codenames="ALL",
    ),
    RoleDefinition(
        slug="admin",
        name="Admin",
        description="Broad administrative access across the tenant dashboard, excluding a few high-risk governance actions.",
        color="#1d4ed8",
        sort_order=2,
        permission_codenames=tuple(
            codename
            for codename in ALL_PERMISSION_CODENAMES
            if codename not in {
                "roles.delete",
                "domains.delete",
                "staff.remove",
                "settings.billing",
            }
        ),
    ),
    RoleDefinition(
        slug="manager",
        name="Manager",
        description="Broad commerce and operations access for day-to-day store management.",
        color="#0369a1",
        sort_order=3,
        permission_codenames=permissions_for_prefixes(
            "dashboard",
            "products",
            "attribute_groups",
            "attributes",
            "categories",
            "brands",
            "tags",
            "pricing",
            "pos",
            "customers",
            "notifications",
            "marketplace",
            exclude={"notifications.manage_webhooks", "marketplace.manage_usage"},
        )
        + (
            "payments.view",
            "payments.request_payout",
            "payments.view_ledger",
            "payments.view_analytics",
            "domains.view",
            "domains.verify",
            "settings.view",
            "settings.edit",
            "settings.theme",
        ),
    ),
    RoleDefinition(
        slug="fulfillment",
        name="Fulfillment",
        description="Focused on selling, stock movement, and fulfilling operational work.",
        color="#0f766e",
        sort_order=4,
        permission_codenames=(
            "dashboard.view",
            "products.view",
            "customers.view",
            "pos.view",
            "pos.sell",
            "pos.manage_inventory",
            "pos.view_reports",
            "payments.view",
            "notifications.view",
            "notifications.view_logs",
        ),
    ),
    RoleDefinition(
        slug="support",
        name="Support",
        description="Focused on customers, disputes, refunds, and communication surfaces.",
        color="#7c3aed",
        sort_order=5,
        permission_codenames=(
            "dashboard.view",
            "customers.view",
            "customers.edit",
            "users.view",
            "payments.view",
            "payments.issue_refund",
            "payments.manage_disputes",
            "notifications.view",
            "notifications.view_logs",
            "notifications.manage_preferences",
            "marketplace.view",
            "marketplace.view_purchases",
            "audit.view",
        ),
    ),
    RoleDefinition(
        slug="analyst",
        name="Analyst",
        description="Read-heavy analytics and oversight access across the store.",
        color="#b45309",
        sort_order=6,
        permission_codenames=(
            "dashboard.view",
            "products.view",
            "pricing.view",
            "payments.view",
            "payments.view_ledger",
            "payments.view_analytics",
            "marketplace.view",
            "marketplace.view_purchases",
            "customers.view",
            "audit.view",
            "audit.export",
            "notifications.view",
            "notifications.view_logs",
            "pos.view",
            "pos.view_reports",
        ),
    ),
)


@lru_cache(maxsize=1)
def permission_definition_map() -> dict[str, PermissionDefinition]:
    return {definition.codename: definition for definition in PERMISSION_DEFINITIONS}


def get_permission_definition(codename: str) -> PermissionDefinition | None:
    return permission_definition_map().get(codename)


def iter_permission_codenames() -> tuple[str, ...]:
    return ALL_PERMISSION_CODENAMES

