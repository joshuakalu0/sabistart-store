from django.contrib import admin

from dashboard.feature_marketplace.models import (
    CouponRedemption,
    FeaturePurchase,
    FeaturePurchaseItem,
    ResourceQuota,
    TenantEntitlement,
    UsageRecord,
)


class FeaturePurchaseItemInline(admin.TabularInline):
    model = FeaturePurchaseItem
    extra = 0


@admin.register(FeaturePurchase)
class FeaturePurchaseAdmin(admin.ModelAdmin):
    list_display = ("purchase_reference", "purchase_type", "status", "gateway_provider", "currency", "total_amount", "created_at")
    list_filter = ("purchase_type", "status", "gateway_provider", "currency")
    search_fields = ("purchase_reference", "feature_code", "bundle_slug", "gateway_reference")
    inlines = [FeaturePurchaseItemInline]


@admin.register(TenantEntitlement)
class TenantEntitlementAdmin(admin.ModelAdmin):
    list_display = ("feature_code", "status", "source", "billing_cycle", "expires_at", "activated_at")
    list_filter = ("feature_type", "status", "source", "billing_cycle")
    search_fields = ("feature_code", "feature_name", "purchase_reference")


@admin.register(ResourceQuota)
class ResourceQuotaAdmin(admin.ModelAdmin):
    list_display = ("resource_type", "total_quota", "used_quota", "updated_at")
    search_fields = ("resource_type",)


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("feature_code", "quantity_used", "used_at")
    list_filter = ("feature_code",)
    search_fields = ("feature_code", "description")


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon_code", "discount_applied", "redeemed_at")
    search_fields = ("coupon_code", "purchase__purchase_reference")
