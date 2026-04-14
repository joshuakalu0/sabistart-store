from django.contrib import admin
from system.core.models import (
    Shop,
    Domain
)
from django_tenants.admin import TenantAdminMixin


@admin.register(Shop)
class ShopAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('name',)


admin.site.register(Domain)
# @admin.register(Shop)
# class ShopAdmin(admin.ModelAdmin):
#     """Admin interface for Shop model (Tenant instances)."""
#     list_display = (
#         'name', 'slug', 'schema_name', 'owner', 'is_active', 'is_suspended', 'is_on_trial',
#         'trial_ends_at', 'created_at'
#     )
#     list_filter = (
#         'is_active', 'is_suspended', 'is_on_trial', 'created_at', 'trial_ends_at'
#     )
#     search_fields = ('name', 'slug', 'schema_name', 'owner__email')
#     readonly_fields = ('id', 'created_at', 'updated_at')
#     ordering = ('-created_at',)
#     list_per_page = 25
#     fieldsets = (
#         ('Identity', {
#             'fields': ('name', 'slug', 'schema_name', 'owner')
#         }),
#         ('Status', {
#             'fields': ('is_active', 'is_suspended', 'suspended_reason')
#         }),
#         ('Trial', {
#             'fields': ('is_on_trial', 'trial_ends_at')
#         }),
#         ('Metadata', {
#             'fields': ('created_at', 'updated_at')
#         }),
#     )


# @admin.register(Domain)
# class DomainAdmin(admin.ModelAdmin):
#     """Admin interface for Domain model (Shop domains)."""
#     list_display = (
#         'domain', 'tenant', 'is_primary', 'is_custom', 'ssl_verified',
#         'created_at', 'verified_at'
#     )
#     list_filter = (
#         'is_primary', 'is_custom', 'ssl_verified', 'created_at'
#     )
#     search_fields = ('domain', 'tenant__name', 'tenant__slug')
#     readonly_fields = ('id', 'created_at', 'verified_at')
#     ordering = ('-is_primary', 'domain')
#     list_per_page = 25
