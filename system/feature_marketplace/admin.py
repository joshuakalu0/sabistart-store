from django.contrib import admin

from system.feature_marketplace.models import (
    BundleItem,
    Coupon,
    DiscountCampaign,
    FeatureBundle,
    FeatureCategory,
    FeatureDefinition,
    FeatureEntitlementIndex,
    FeaturePrice,
    FeaturePurchaseIndex,
    TenantFeatureOverride,
)


class FeaturePriceInline(admin.TabularInline):
    model = FeaturePrice
    extra = 0


class BundleItemInline(admin.TabularInline):
    model = BundleItem
    extra = 0


@admin.register(FeatureCategory)
class FeatureCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "display_order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(FeatureDefinition)
class FeatureDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "feature_type", "is_active", "is_purchasable", "is_featured")
    list_filter = ("feature_type", "is_active", "is_purchasable", "is_featured", "is_globally_enabled", "is_globally_disabled")
    search_fields = ("name", "code", "short_description")
    prepopulated_fields = {"code": ("name",)}
    inlines = [FeaturePriceInline]


@admin.register(FeaturePrice)
class FeaturePriceAdmin(admin.ModelAdmin):
    list_display = ("feature", "currency", "billing_cycle", "amount", "is_active")
    list_filter = ("currency", "billing_cycle", "is_active")
    search_fields = ("feature__name", "feature__code", "display_name")


@admin.register(FeatureBundle)
class FeatureBundleAdmin(admin.ModelAdmin):
    list_display = ("name", "currency", "price", "billing_cycle", "is_active", "is_featured")
    list_filter = ("currency", "billing_cycle", "is_active", "is_featured")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [BundleItemInline]


@admin.register(DiscountCampaign)
class DiscountCampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "discount_type", "discount_value", "is_active", "valid_from", "valid_until")
    list_filter = ("discount_type", "is_active")
    search_fields = ("name", "description")
    filter_horizontal = ("applicable_features", "applicable_bundles")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "discount_value", "is_active", "current_uses", "max_uses")
    list_filter = ("discount_type", "is_active")
    search_fields = ("code", "description")
    filter_horizontal = ("applicable_features", "applicable_bundles")


@admin.register(FeaturePurchaseIndex)
class FeaturePurchaseIndexAdmin(admin.ModelAdmin):
    list_display = ("purchase_reference", "schema_name", "gateway_provider", "status", "created_at")
    list_filter = ("status", "gateway_provider")
    search_fields = ("purchase_reference", "schema_name", "gateway_reference")


@admin.register(TenantFeatureOverride)
class TenantFeatureOverrideAdmin(admin.ModelAdmin):
    list_display = ("schema_name", "feature", "mode", "currency", "billing_cycle", "is_active", "effective_from", "effective_until")
    list_filter = ("mode", "is_active", "currency", "billing_cycle")
    search_fields = ("schema_name", "feature__name", "feature__code", "notes")


@admin.register(FeatureEntitlementIndex)
class FeatureEntitlementIndexAdmin(admin.ModelAdmin):
    list_display = ("schema_name", "feature_code", "feature_name", "status", "source", "billing_cycle", "currency", "expires_at", "last_synced_at")
    list_filter = ("feature_type", "status", "source", "billing_cycle", "currency")
    search_fields = ("schema_name", "feature_code", "feature_name", "purchase_reference")
