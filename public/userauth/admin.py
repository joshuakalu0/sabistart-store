# from django.contrib import admin
# from account.models import (
#     PlatformUser,
#     PlatformStaff,
#     TenantUser,
#     Customer,
#     CustomerAddress
# )


# @admin.register(PlatformUser)
# class PlatformUserAdmin(admin.ModelAdmin):
#     """Admin interface for PlatformUser model."""
#     list_display = ('email', 'first_name', 'last_name',
#                     'is_active', 'is_staff', 'created_at')
#     list_filter = ('is_active', 'is_staff', 'created_at')
#     search_fields = ('email', 'first_name', 'last_name')
#     readonly_fields = ('id', 'created_at', 'updated_at')
#     ordering = ('-created_at',)
#     list_per_page = 25


# @admin.register(PlatformStaff)
# class PlatformStaffAdmin(admin.ModelAdmin):
#     """Admin interface for PlatformStaff model."""
#     list_display = ('user', 'role',)
#     list_filter = ('role',)
#     search_fields = ('user__email', 'user__first_name', 'user__last_name')
#     readonly_fields = ('user',)


# @admin.register(TenantUser)
# class TenantUserAdmin(admin.ModelAdmin):
#     """Admin interface for TenantUser model."""
#     list_display = ('email', 'first_name', 'last_name',
#                     'is_active', 'is_staff', 'created_at')
#     list_filter = ('is_active', 'is_staff', 'created_at')
#     search_fields = ('email', 'first_name', 'last_name')
#     readonly_fields = ('id', 'created_at', 'updated_at')
#     ordering = ('-created_at',)
#     list_per_page = 25


# @admin.register(Customer)
# class CustomerAdmin(admin.ModelAdmin):
#     """Admin interface for Customer model."""
#     list_display = ('user', 'email_verified',)
#     list_filter = ('email_verified',)
#     search_fields = ('user__email', 'user__first_name',
#                      'user__last_name', 'phone')
#     readonly_fields = ('user',)


# @admin.register(CustomerAddress)
# class CustomerAddressAdmin(admin.ModelAdmin):
#     """Admin interface for CustomerAddress model."""
#     list_display = ('customer', 'full_name', 'phone',
#                     'city', 'country', 'is_default')
#     list_filter = ('is_default', 'country', 'city')
#     search_fields = ('customer__user__email', 'full_name',
#                      'phone', 'city', 'country', 'postal_code')
#     readonly_fields = ('id', 'created_at', 'updated_at')
#     ordering = ('-created_at',)
