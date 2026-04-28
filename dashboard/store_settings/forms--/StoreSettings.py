import logging
import json
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import StoreSettings

logger = logging.getLogger(__name__)


class StoreSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Store Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = StoreSettings
        exclude = ['id', 'created_at', 'updated_at']
        widgets = {
            # === GENERAL SETTINGS ===
            'store_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Acme Store'
            }),
            'store_tagline': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Quality Products, Great Prices'
            }),
            'store_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe your store...'
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'contact@example.com'
            }),
            'support_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'support@example.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1 (555) 123-4567'
            }),
            'whatsapp_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1 (555) 123-4567'
            }),
            'address_line1': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line2': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'currency_position': forms.Select(attrs={'class': 'form-select'}),
            'timezone': forms.Select(attrs={'class': 'form-select'}),
            'maintenance_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'maintenance_message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'pagination_items_per_page': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 10,
                'max': 500
            }),
            'apple_store_link': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://apps.apple.com/...'
            }),
            'play_store_link': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://play.google.com/...'
            }),

            # === BRANDING ===
            'logo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/svg+xml'
            }),
            'logo_dark': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/svg+xml'
            }),
            'favicon': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/x-icon,image/png,image/svg+xml'
            }),
            'loading_gif': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/gif'
            }),

            # === SEO ===
            'meta_title': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': 60,
                'placeholder': 'Max 60 characters'
            }),
            'meta_description': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': 160,
                'placeholder': 'Max 160 characters'
            }),
            'meta_keywords': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'keyword1, keyword2, keyword3'
            }),
            'robots_txt': forms.Textarea(attrs={
                'class': 'form-control font-mono',
                'rows': 6
            }),
            'allow_indexing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sitemap_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'google_analytics_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'G-XXXXXXXXXX'
            }),
            'google_tag_manager_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'GTM-XXXXXXX'
            }),
            'facebook_pixel_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '1234567890'
            }),

            # === SHIPPING ===
            'shipping_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'free_shipping_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'free_shipping_threshold': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'use_live_rates': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'processing_time_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 365
            }),
            'allow_local_pickup': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ship_to_po_boxes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'require_signature': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === TAX ===
            'tax_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'prices_include_tax': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tax_calculation_method': forms.Select(attrs={'class': 'form-select'}),
            'default_tax_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'charge_tax_on_shipping': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tax_id_number': forms.TextInput(attrs={'class': 'form-control'}),
            'show_privacy_policy': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_terms_of_service': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_refund_policy': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_shipping_policy': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === CHECKOUT ===
            'allow_guest_checkout': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cart_expiry_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 365
            }),
            'validate_address': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dashboard_path_prefix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'admin'
            }),

            # === FEATURES ===
            'enable_reviews': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_wishlist': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_compare': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_gift_cards': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_subscriptions': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_social_login': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_social_sharing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_popup': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_discount_codes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_live_chat': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'live_chat_provider': forms.TextInput(attrs={'class': 'form-control'}),
            'enable_api_access': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_webhooks': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_contact_email(self):
        """Validate contact email."""
        email = self.cleaned_data.get('contact_email')
        if email and not email.strip():
            raise ValidationError(_("Contact email cannot be empty."))
        return email

    def clean_support_email(self):
        """Validate support email if provided."""
        email = self.cleaned_data.get('support_email')
        if email and not email.strip():
            raise ValidationError(
                _("Support email cannot be empty if provided."))
        return email

    def clean_phone(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('phone')
        if phone:
            import re
            phone_clean = re.sub(r'[^\d+]', '', phone)
            if len(phone_clean) < 10:
                raise ValidationError(
                    _("Phone number must be at least 10 digits."))
        return phone

    def clean_latitude(self):
        """Validate latitude range."""
        lat = self.cleaned_data.get('latitude')
        if lat is not None and not (-90 <= lat <= 90):
            raise ValidationError(_("Latitude must be between -90 and 90."))
        return lat

    def clean_longitude(self):
        """Validate longitude range."""
        lon = self.cleaned_data.get('longitude')
        if lon is not None and not (-180 <= lon <= 180):
            raise ValidationError(_("Longitude must be between -180 and 180."))
        return lon

    def clean_meta_title(self):
        """Validate meta title length for SEO."""
        title = self.cleaned_data.get('meta_title')
        if title and len(title) > 60:
            raise ValidationError(
                _("Meta title should not exceed 60 characters for SEO."))
        return title

    def clean_meta_description(self):
        """Validate meta description length for SEO."""
        desc = self.cleaned_data.get('meta_description')
        if desc and len(desc) > 160:
            raise ValidationError(
                _("Meta description should not exceed 160 characters for SEO."))
        return desc

    def clean_free_shipping_threshold(self):
        """Validate free shipping threshold."""
        threshold = self.cleaned_data.get('free_shipping_threshold')
        enabled = self.cleaned_data.get('free_shipping_enabled')
        if enabled and threshold is not None and threshold <= 0:
            raise ValidationError(
                _("Free shipping threshold must be greater than 0."))
        return threshold

    def clean_default_tax_rate(self):
        """Validate tax rate."""
        rate = self.cleaned_data.get('default_tax_rate')
        enabled = self.cleaned_data.get('tax_enabled')
        if enabled and rate is not None and rate < 0:
            raise ValidationError(_("Tax rate cannot be negative."))
        return rate

    def clean_dashboard_path_prefix(self):
        """Validate dashboard path prefix for security."""
        prefix = self.cleaned_data.get('dashboard_path_prefix')
        if prefix:
            # Prevent common admin path guesses
            common_paths = ['admin', 'wp-admin',
                            'administrator', 'login', 'dashboard']
            if prefix.lower() in common_paths:
                logger.warning(f"Common admin path used: {prefix}")
                # Don't raise error, just warn
        return prefix

    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()

        # Validate email consistency
        contact_email = cleaned_data.get('contact_email')
        support_email = cleaned_data.get('support_email')
        if contact_email and support_email and contact_email == support_email:
            logger.info("Contact and support emails are the same.")

        return cleaned_data

    def save(self, commit=True):
        """Save and invalidate cache."""
        instance = super().save(commit=commit)

        # Invalidate cache
        from django.core.cache import cache
        from django.db import connection
        cache_key = f'store_settings_{connection.schema_name}'
        cache.delete(cache_key)

        logger.info(
            f"StoreSettings saved for tenant: {connection.schema_name}")
        return instance
