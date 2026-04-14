"""
Professional Settings Forms
Comprehensive form classes with validation and modern widgets
"""

from django import forms
from django.core.exceptions import ValidationError
from public.store_settings.models import StoreSettings
import re


class BaseSettingsForm(forms.ModelForm):
    """Base form with common functionality."""

    class Meta:
        model = StoreSettings
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add common CSS classes to all fields for Tailwind design
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg py-2.5 px-4 text-sm focus:ring-primary focus:border-primary transition-colors'
            })


class GeneralSettingsForm(BaseSettingsForm):
    """Form for general store settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'store_name', 'store_tagline', 'store_description',
            'contact_email', 'support_email', 'phone',
            'address_line1', 'address_line2', 'city', 'state', 'country', 'postal_code',
            'latitude', 'longitude',
            'default_language', 'default_currency', 'currency_position', 'time_zone',
            'store_status', 'maintenance_mode', 'maintenance_message',
            'pagination_items_per_page', 'business_model',
            'facebook_url', 'instagram_url', 'twitter_url', 'linkedin_url',
            'copyright_text', 'apple_store_link', 'play_store_link',
            'primary_color', 'secondary_color'
        ]
        widgets = {
            'store_description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Describe your store...'
            }),
            'maintenance_message': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'We are currently under maintenance. Please check back soon.'
            }),
            'phone': forms.TextInput(attrs={
                'placeholder': '+1 (555) 123-4567'
            }),
            'address_line1': forms.TextInput(attrs={
                'placeholder': 'Street address'
            }),
            'address_line2': forms.TextInput(attrs={
                'placeholder': 'Apartment, suite, etc. (optional)'
            }),
            'city': forms.TextInput(attrs={
                'placeholder': 'City'
            }),
            'state': forms.TextInput(attrs={
                'placeholder': 'State/Province'
            }),
            'postal_code': forms.TextInput(attrs={
                'placeholder': 'Postal code'
            }),
            'latitude': forms.NumberInput(attrs={
                'step': '0.000001',
                'placeholder': 'e.g., 40.712776'
            }),
            'longitude': forms.NumberInput(attrs={
                'step': '0.000001',
                'placeholder': 'e.g., -74.005974'
            }),
            'maintenance_mode': forms.CheckboxInput(attrs={
                'class': 'sr-only peer'
            }),
            'primary_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'w-16 h-16 rounded-lg cursor-pointer border-none p-0 overflow-hidden'
            }),
            'secondary_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'w-16 h-16 rounded-lg cursor-pointer border-none p-0 overflow-hidden'
            }),
            'copyright_text': forms.Textarea(attrs={
                'rows': 3
            }),
            'facebook_url': forms.URLInput(attrs={
                'placeholder': 'https://facebook.com/yourbusiness'
            }),
            'instagram_url': forms.URLInput(attrs={
                'placeholder': 'https://instagram.com/yourbusiness'
            }),
            'twitter_url': forms.URLInput(attrs={
                'placeholder': 'https://twitter.com/yourbusiness'
            }),
            'linkedin_url': forms.URLInput(attrs={
                'placeholder': 'https://linkedin.com/company/yourbusiness'
            }),
            'apple_store_link': forms.URLInput(attrs={
                'placeholder': 'https://apps.apple.com/...'
            }),
            'play_store_link': forms.URLInput(attrs={
                'placeholder': 'https://play.google.com/store/...'
            }),
        }
        widgets = {
            'store_description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Describe your store...'
            }),
            'maintenance_message': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'We are currently under maintenance. Please check back soon.'
            }),
            'phone': forms.TextInput(attrs={
                'placeholder': '+1 (555) 123-4567'
            }),
            'address_line1': forms.TextInput(attrs={
                'placeholder': 'Street address'
            }),
            'address_line2': forms.TextInput(attrs={
                'placeholder': 'Apartment, suite, etc. (optional)'
            }),
            'city': forms.TextInput(attrs={
                'placeholder': 'City'
            }),
            'state': forms.TextInput(attrs={
                'placeholder': 'State/Province'
            }),
            'postal_code': forms.TextInput(attrs={
                'placeholder': 'Postal code'
            }),
            'latitude': forms.NumberInput(attrs={
                'step': '0.000001',
                'placeholder': 'e.g., 40.712776'
            }),
            'longitude': forms.NumberInput(attrs={
                'step': '0.000001',
                'placeholder': 'e.g., -74.005974'
            }),
            'maintenance_mode': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
        }
        labels = {
            'store_name': 'Company Name',
            'store_tagline': 'Tagline',
            'store_description': 'Description',
            'contact_email': 'Email',
            'support_email': 'Support Email',
            'phone': 'Phone',
            'address_line1': 'Address',
            'address_line2': 'Address Line 2',
            'default_language': 'Language',
            'default_currency': 'Currency',
            'time_zone': 'Time Zone',
            'pagination_items_per_page': 'Pagination',
        }

    def clean_phone(self):
        """Validate phone number."""
        phone = self.cleaned_data.get('phone')
        if phone:
            # Remove all non-digit characters except +
            phone_clean = re.sub(r'[^\d+]', '', phone)
            if len(phone_clean) < 10:
                raise ValidationError(
                    "Phone number must be at least 10 digits.")
        return phone

    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()

        # If maintenance mode is enabled, require a message
        if cleaned_data.get('maintenance_mode') and not cleaned_data.get('maintenance_message'):
            self.add_error(
                'maintenance_message', 'Maintenance message is required when maintenance mode is enabled.')

        # Validate coordinates together
        lat = cleaned_data.get('latitude')
        lon = cleaned_data.get('longitude')
        if (lat is not None and lon is None) or (lat is None and lon is not None):
            raise ValidationError(
                "Both latitude and longitude must be provided together.")

        return cleaned_data


class BrandingSettingsForm(BaseSettingsForm):
    """Form for branding and appearance settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'logo', 'logo_dark', 'favicon', 'loading_gif',
            'primary_color', 'secondary_color', 'accent_color',
            'background_color', 'text_color',
            'heading_font', 'body_font',
            'layout_style'
        ]
        widgets = {
            'primary_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color'
            }),
            'secondary_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color'
            }),
            'accent_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color'
            }),
            'background_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color'
            }),
            'text_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color'
            }),
        }


class SEOSettingsForm(BaseSettingsForm):
    """Form for SEO and analytics settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'custom_domain',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image',
            'robots_txt', 'allow_indexing', 'sitemap_enabled',
            'google_analytics_id', 'google_tag_manager_id', 'facebook_pixel_id'
        ]
        widgets = {
            'meta_description': forms.Textarea(attrs={
                'rows': 3,
                'maxlength': 160,
                'placeholder': 'Brief description for search engines (max 160 characters)'
            }),
            'og_description': forms.Textarea(attrs={
                'rows': 3,
                'maxlength': 160
            }),
            'robots_txt': forms.Textarea(attrs={
                'rows': 6,
                'placeholder': 'User-agent: *\nDisallow: /admin/'
            }),
            'allow_indexing': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
            'sitemap_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
        }


class PaymentSettingsForm(BaseSettingsForm):
    """Form for payment gateway settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'payment_test_mode',
            'stripe_enabled', 'stripe_publishable_key', 'stripe_secret_key', 'stripe_webhook_secret',
            'paypal_enabled', 'paypal_client_id', 'paypal_secret',
            'cash_on_delivery_enabled', 'bank_transfer_enabled',
            'default_payment_method', 'accept_partial_payments'
        ]
        widgets = {
            'stripe_secret_key': forms.PasswordInput(attrs={
                'render_value': True,
                'placeholder': 'sk_test_...'
            }),
            'stripe_webhook_secret': forms.PasswordInput(attrs={
                'render_value': True,
                'placeholder': 'whsec_...'
            }),
            'paypal_secret': forms.PasswordInput(attrs={
                'render_value': True
            }),
            'payment_test_mode': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
            'stripe_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
            'paypal_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
            'cash_on_delivery_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
            'bank_transfer_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
            'accept_partial_payments': forms.CheckboxInput(attrs={
                'class': 'form-check-input toggle-switch'
            }),
        }


class ShippingSettingsForm(BaseSettingsForm):
    """Form for shipping settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'shipping_enabled',
            'free_shipping_enabled', 'free_shipping_threshold',
            'flat_rate_enabled', 'flat_rate_amount',
            'use_live_rates',
            'processing_time_days', 'allow_local_pickup',
            'ship_to_po_boxes', 'require_signature'
        ]
        widgets = {
            'shipping_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'free_shipping_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'flat_rate_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'use_live_rates': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'allow_local_pickup': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'ship_to_po_boxes': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_signature': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
        }


class TaxSettingsForm(BaseSettingsForm):
    """Form for tax settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'tax_enabled', 'prices_include_tax',
            'tax_calculation_method', 'default_tax_rate',
            'charge_tax_on_shipping', 'tax_id_number'
        ]
        widgets = {
            'tax_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'prices_include_tax': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'charge_tax_on_shipping': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
        }


class NotificationSettingsForm(BaseSettingsForm):
    """Form for notification settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'email_notifications_enabled', 'from_email', 'from_name',
            'notify_new_order', 'notify_order_shipped', 'notify_order_delivered', 'notify_order_cancelled',
            'send_order_confirmation', 'send_shipping_confirmation', 'send_delivery_confirmation',
            'low_stock_alert_enabled', 'low_stock_threshold', 'out_of_stock_alert_enabled',
            'sms_notifications_enabled', 'sms_provider'
        ]
        widgets = {
            'email_notifications_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'notify_new_order': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'notify_order_shipped': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'notify_order_delivered': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'notify_order_cancelled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'send_order_confirmation': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'send_shipping_confirmation': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'send_delivery_confirmation': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'low_stock_alert_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'out_of_stock_alert_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'sms_notifications_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
        }


class PolicySettingsForm(BaseSettingsForm):
    """Form for policy settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'privacy_policy', 'terms_of_service', 'refund_policy', 'shipping_policy',
            'show_privacy_policy', 'show_terms_of_service', 'show_refund_policy', 'show_shipping_policy'
        ]
        widgets = {
            'privacy_policy': forms.Textarea(attrs={'rows': 10}),
            'terms_of_service': forms.Textarea(attrs={'rows': 10}),
            'refund_policy': forms.Textarea(attrs={'rows': 10}),
            'shipping_policy': forms.Textarea(attrs={'rows': 10}),
            'show_privacy_policy': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'show_terms_of_service': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'show_refund_policy': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'show_shipping_policy': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
        }


class CheckoutSettingsForm(BaseSettingsForm):
    """Form for checkout settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'allow_guest_checkout',
            'require_phone', 'require_company', 'require_address_line2',
            'cart_expiry_days', 'show_cart_on_add',
            'allow_order_notes', 'require_order_notes',
            'validate_address',
            'minimum_order_enabled', 'minimum_order_amount'
        ]
        widgets = {
            'allow_guest_checkout': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_phone': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_company': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_address_line2': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'show_cart_on_add': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'allow_order_notes': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_order_notes': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'validate_address': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'minimum_order_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
        }


class SecuritySettingsForm(BaseSettingsForm):
    """Form for security settings."""

    class Meta:
        model = StoreSettings
        fields = [
            'min_password_length', 'require_uppercase', 'require_lowercase',
            'require_numbers', 'require_special_chars',
            'session_timeout_minutes', 'customer_session_timeout_minutes',
            'enable_2fa', 'require_2fa_for_staff',
            'max_login_attempts', 'lockout_duration_minutes',
            'enable_gdpr_mode', 'data_retention_days'
        ]
        widgets = {
            'require_uppercase': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_lowercase': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_numbers': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_special_chars': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_2fa': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'require_2fa_for_staff': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_gdpr_mode': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
        }


class FeatureSettingsForm(BaseSettingsForm):
    """Form for feature toggles."""

    class Meta:
        model = StoreSettings
        fields = [
            'enable_reviews', 'enable_wishlist', 'enable_compare',
            'enable_gift_cards', 'enable_subscriptions',
            'enable_social_login', 'enable_social_sharing',
            'enable_newsletter', 'enable_popup', 'enable_discount_codes',
            'enable_live_chat', 'live_chat_provider',
            'enable_api_access', 'enable_webhooks'
        ]
        widgets = {
            'enable_reviews': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_wishlist': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_compare': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_gift_cards': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_subscriptions': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_social_login': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_social_sharing': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_newsletter': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_popup': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_discount_codes': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_live_chat': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_api_access': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
            'enable_webhooks': forms.CheckboxInput(attrs={'class': 'form-check-input toggle-switch'}),
        }
