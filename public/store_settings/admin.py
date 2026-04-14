# """
# Store Settings Admin Configuration
# """

from django.contrib import admin
from .models import StoreSettings


admin.site.register(StoreSettings)

# @admin.register(StoreSettings)
# class StoreSettingsAdmin(admin.ModelAdmin):
#     """Admin interface for store settings."""

#     list_display = ['store_name', 'contact_email',
#                     'store_status', 'updated_at']
#     search_fields = ['store_name', 'contact_email']
#     list_filter = ['store_status', 'maintenance_mode', 'created_at']

#     fieldsets = (
#         ('General Information', {
#             'fields': (
#                 'store_name', 'store_tagline', 'store_description',
#                 'contact_email', 'support_email', 'phone'
#             )
#         }),
#         ('Address', {
#             'fields': (
#                 'address_line1', 'address_line2', 'city', 'state',
#                 'country', 'postal_code', 'latitude', 'longitude'
#             )
#         }),
#         ('Localization', {
#             'fields': ('default_language', 'default_currency', 'time_zone')
#         }),
#         ('Status', {
#             'fields': ('store_status', 'maintenance_mode', 'maintenance_message')
#         }),
#         ('Branding', {
#             'fields': (
#                 'logo', 'logo_dark', 'favicon',
#                 'primary_color', 'secondary_color', 'accent_color',
#                 'background_color', 'text_color',
#                 'heading_font', 'body_font', 'layout_style'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('SEO', {
#             'fields': (
#                 'custom_domain', 'meta_title', 'meta_description', 'meta_keywords',
#                 'og_title', 'og_description', 'og_image',
#                 'robots_txt', 'allow_indexing', 'sitemap_enabled',
#                 'google_analytics_id', 'google_tag_manager_id', 'facebook_pixel_id'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Payment', {
#             'fields': (
#                 'payment_test_mode',
#                 'stripe_enabled', 'stripe_publishable_key', 'stripe_secret_key', 'stripe_webhook_secret',
#                 'paypal_enabled', 'paypal_client_id', 'paypal_secret',
#                 'cash_on_delivery_enabled', 'bank_transfer_enabled',
#                 'default_payment_method', 'accept_partial_payments'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Shipping', {
#             'fields': (
#                 'shipping_enabled',
#                 'free_shipping_enabled', 'free_shipping_threshold',
#                 'flat_rate_enabled', 'flat_rate_amount',
#                 'use_live_rates',
#                 'processing_time_days', 'allow_local_pickup',
#                 'ship_to_po_boxes', 'require_signature'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Tax', {
#             'fields': (
#                 'tax_enabled', 'prices_include_tax',
#                 'tax_calculation_method', 'default_tax_rate',
#                 'charge_tax_on_shipping', 'tax_id_number'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Notifications', {
#             'fields': (
#                 'email_notifications_enabled', 'from_email', 'from_name',
#                 'notify_new_order', 'notify_order_shipped', 'notify_order_delivered', 'notify_order_cancelled',
#                 'send_order_confirmation', 'send_shipping_confirmation', 'send_delivery_confirmation',
#                 'low_stock_alert_enabled', 'low_stock_threshold', 'out_of_stock_alert_enabled',
#                 'sms_notifications_enabled', 'sms_provider'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Policies', {
#             'fields': (
#                 'privacy_policy', 'terms_of_service', 'refund_policy', 'shipping_policy',
#                 'show_privacy_policy', 'show_terms_of_service', 'show_refund_policy', 'show_shipping_policy'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Checkout', {
#             'fields': (
#                 'allow_guest_checkout',
#                 'require_phone', 'require_company', 'require_address_line2',
#                 'cart_expiry_days', 'show_cart_on_add',
#                 'allow_order_notes', 'require_order_notes',
#                 'validate_address',
#                 'minimum_order_enabled', 'minimum_order_amount'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Security', {
#             'fields': (
#                 'min_password_length', 'require_uppercase', 'require_lowercase',
#                 'require_numbers', 'require_special_chars',
#                 'session_timeout_minutes', 'customer_session_timeout_minutes',
#                 'enable_2fa', 'require_2fa_for_staff',
#                 'max_login_attempts', 'lockout_duration_minutes',
#                 'enable_gdpr_mode', 'data_retention_days'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Features', {
#             'fields': (
#                 'enable_reviews', 'enable_wishlist', 'enable_compare',
#                 'enable_gift_cards', 'enable_subscriptions',
#                 'enable_social_login', 'enable_social_sharing',
#                 'enable_newsletter', 'enable_popup', 'enable_discount_codes',
#                 'enable_live_chat', 'live_chat_provider',
#                 'enable_api_access', 'enable_webhooks'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Metadata', {
#             'fields': ('created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )

#     readonly_fields = ['created_at', 'updated_at']

#     def has_add_permission(self, request):
#         """Only allow one settings instance."""
#         return not StoreSettings.objects.exists()

#     def has_delete_permission(self, request, obj=None):
#         """Prevent deletion of settings."""
#         return False
