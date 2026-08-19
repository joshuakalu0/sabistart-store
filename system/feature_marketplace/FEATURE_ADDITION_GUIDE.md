# Adding a New Billable Feature

This guide shows the complete path for adding a new billable feature to the platform using the live marketplace and entitlement architecture in this repository.

Worked example:
`Web Scraping Feature`

Goal:
Allow a tenant to paste a product-source URL, scrape product data from an external site, and import that data into the tenant product catalog. Access must be paid and enforced by the marketplace.

## 1. Decide the feature shape first

Before you write any business logic, decide whether the capability is:

- `boolean`: the tenant either has access or does not
- `limit`: the tenant gets a numeric capacity
- `usage`: the tenant gets consumable credits

For web scraping, the clean pattern is:

- `product_scraper` as a `boolean` unlock for the UI and workflow
- `import_credits` or `scrape_jobs` as a `usage` or `limit` feature if each import should consume capacity

Use this split whenever the feature has both:

- access control
- a billable consumption model

## 2. Add the platform catalog definition

The public feature catalog lives in:

- `system/feature_marketplace/models.py`
- `system/feature_marketplace/catalog_registry.py`

### Add the seed definition

Add the feature entry in `system.feature_marketplace.catalog_registry`.

For `product_scraper`, define:

- `code`
- `name`
- `feature_type`
- category metadata
- default values
- storefront or dashboard mapping metadata
- pricing definitions

Example decisions:

- `product_scraper`
  - type: `boolean`
  - default: `False`
  - purchasable: `True`
  - sidebar key: optional if you want it tied to a dashboard nav section

- `import_credits`
  - type: `usage`
  - default: `0`
  - priced as one-time credit packs or monthly allocations

Then rerun:

```powershell
.\.venv\Scripts\python.exe manage.py seed_feature_catalog --profile realistic-plus
```

That updates `FeatureDefinition`, `FeaturePrice`, bundles, campaigns, and coupons in the public schema.

### Platform editing after seeding

Platform admins can still edit the live public records from:

- `/platform/features/features/<code>/`
- `/platform/features/pricing/`
- `/platform/features/bundles/`
- `/platform/features/campaigns/`
- `/platform/features/coupons/`

The seed registry gives you a repeatable default, but the public marketplace remains the live control plane.

## 3. Add tenant-side entitlement bindings

The entitlement integration registry lives in:

- `dashboard/feature_marketplace/integration_registry.py`

Add the new feature to the appropriate registry entry:

- nav bindings
- settings bindings
- storefront flag bindings
- quota counters
- upgrade copy

For `product_scraper`:

- add a feature-to-setting or feature-to-nav mapping if the tenant dashboard should expose a scraping section
- add a usage binding if the workflow consumes credits

This registry is what keeps future features low-friction. The workflow is:

1. add catalog seed definition
2. add entitlement integration binding
3. wire guarded UI and service logic
4. rerun seed

## 4. Build the actual feature app

Put the real implementation in the app that owns the business domain.

For the scraping example, a good home would be a dedicated tenant app such as:

- `dashboard/product_importer`
- or `dashboard/product_tools`

Inside that app, add:

- `views.py`
- `services.py`
- `forms.py`
- `urls.py`
- tenant templates under `templates/dashboard/...`

Keep business logic in services, not in views.

For example:

- `start_scrape_job(...)`
- `preview_scraped_products(...)`
- `import_scraped_products(...)`

If scraping becomes asynchronous, the Celery task should live near that feature app while entitlement checks remain in the shared marketplace engine.

## 5. Gate the feature correctly

The runtime authority is:

- `dashboard.feature_marketplace.services.engine.FeatureEntitlementEngine`

Use the shared guards instead of ad hoc checks:

- `require_feature(code)`
- `enforce_quota(code, requested)`
- `require_usage_balance(code, amount)`
- `consume_feature_usage(code, amount)`

### Boolean unlock example

If the scraper page should only exist for paying tenants:

```python
@login_required
@dashboard_prefix_required
@require_feature("product_scraper")
def scrape_dashboard(request, prefix):
    ...
```

### Usage-credit example

If each import run consumes credits:

```python
engine = get_engine_for_request(request)
require_usage_balance("import_credits", amount=1, engine=engine)
engine.consume_feature_usage("import_credits", amount=1, description="Product scrape import")
```

Do both:

- hide the UI when the feature is missing
- block the action on the server even if someone hits the URL directly

## 6. Expose the feature in the tenant dashboard

Tenant navigation is defined in:

- `sabistart/navigation.py`

Add a real navigation entry with:

- `key`
- `name`
- `icon`
- `route`
- `feature_code`
- `active_keys`

Example:

```python
{
    "key": "product_scraper",
    "name": "Product Scraper",
    "icon": "download",
    "route": "dashboard:product_importer:home",
    "feature_code": "product_scraper",
    "active_keys": ("product_scraper",),
}
```

Because the tenant sidebar already filters items through the entitlement engine, the feature will disappear automatically for tenants who do not have access.

Then add the actual route to the owning app and include it under the dashboard prefix if it is not already wired.

## 7. Add billing and purchase support

Standalone billing lives in the marketplace, not in the feature app.

The purchase lifecycle is:

1. tenant browses `/dashboard/<prefix>/marketplace/`
2. tenant previews price via marketplace services
3. tenant creates a pending `FeaturePurchase`
4. public `FeaturePurchaseIndex` maps purchase to tenant schema
5. platform payment route resolves the purchase
6. marketplace activation creates tenant entitlements

Important files:

- `system/feature_marketplace/services.py`
- `dashboard/feature_marketplace/services/checkout.py`
- `dashboard/feature_marketplace/services/engine.py`
- `system/system_pay/services.py`

If the feature should be sold alone:

- add a `FeaturePrice`

If it should be bundled:

- add it to a `FeatureBundle`

If it should be discounted:

- add a `DiscountCampaign` or `Coupon`

## 8. Add it to bundles or plans

Bundles are public schema records:

- `FeatureBundle`
- `BundleItem`

To include `product_scraper` in a plan like `growth-plan`:

1. add a `BundleItem` pointing at the feature
2. if needed, also add `import_credits` with `quantity_override`
3. seed or edit the bundle from `/platform/features/bundles/`

This keeps plan composition entirely in the marketplace control plane instead of scattering plan logic across tenant apps.

## 9. Add tests end to end

Every new billable feature should have tests in three layers:

### Catalog and preview

Test that:

- the feature exists in the public catalog
- pricing resolves correctly
- bundles include the feature
- coupons and campaigns apply correctly

### Entitlement enforcement

Test that:

- tenants without entitlement cannot access the route
- tenants with entitlement can access it
- usage or limit consumption behaves correctly

### Business workflow

Test the actual feature app:

- scraping preview works
- import creates products correctly
- credits are consumed only on success

Use the existing marketplace tests as a pattern:

- `dashboard/feature_marketplace/tests.py`

## 10. Grandfathering existing tenants

If the feature replaces an already-open setting, add it to the grandfather workflow before you enforce the lock.

Relevant command:

- `system/feature_marketplace/management/commands/grandfather_feature_entitlements.py`

If a legacy open toggle exists, add migration logic that grants:

- perpetual boolean access
- or sufficient limit/usage capacity

Then run grandfathering before removing any legacy fallback behavior.

## 11. Changing pricing later

Do not mutate tenant entitlements to “fix” pricing.

Instead:

1. update or add the relevant `FeaturePrice`
2. keep existing entitlements intact
3. let new purchases use the new price

This avoids breaking historical purchases and keeps entitlement history stable.

If you need tenant-specific commercial treatment, use:

- `TenantFeatureOverride`

Available override modes include:

- force enabled
- force disabled
- free
- custom price
- discount percent
- discount amount

## 12. Retiring a feature safely

If the feature must be deprecated:

1. mark it inactive or not purchasable in `FeatureDefinition`
2. remove it from bundles and campaigns
3. keep existing entitlements readable
4. decide whether current tenants retain access until expiry or are migrated elsewhere
5. update navigation and UI copy
6. write a migration path if the capability is being replaced

Do not hard-delete the feature if tenant entitlements or historical purchases depend on it.

## 13. Practical checklist

For every new billable feature, complete this checklist:

1. Add seed definition in `system.feature_marketplace.catalog_registry`
2. Add integration binding in `dashboard.feature_marketplace.integration_registry`
3. Build tenant app logic and templates
4. Protect routes and actions with the entitlement engine
5. Add dashboard navigation entry with `feature_code`
6. Seed the catalog
7. Add bundle/coupon/campaign support if needed
8. Add tests
9. Add grandfather logic if replacing a legacy open capability
10. Run checks and verify purchase, activation, and access

That is the supported path from concept to live billable capability in this codebase.
