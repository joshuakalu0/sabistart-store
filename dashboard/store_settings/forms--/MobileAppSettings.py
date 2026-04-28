import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import MobileAppSettings

logger = logging.getLogger(__name__)


class MobileAppSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Mobile App Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = MobileAppSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === APP IDENTITY ===
            'app_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., My Store App'
            }),
            'app_tagline': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Shop anytime, anywhere'
            }),
            'app_icon': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg'
            }),
            'splash_screen': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg'
            }),
            'splash_screen_duration': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 5
            }),

            # === THEME ===
            'primary_color': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'accent_color': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'background_color': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'status_bar_style': forms.Select(attrs={'class': 'form-select'}),
            'enable_dark_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === NAVIGATION ===
            'bottom_nav_style': forms.Select(attrs={'class': 'form-select'}),
            'show_home_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_categories_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_search_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_cart_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_account_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_wishlist_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_bottom_nav_items': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 3,
                'max': 6
            }),

            # === PUSH NOTIFICATIONS ===
            'enable_push_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'firebase_server_key': forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'Firebase server key'
            }),
            'apns_certificate': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.p8,.pem,.p12'
            }),
            'notify_order_updates': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_promotions': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_new_products': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_price_drops': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_back_in_stock': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_abandoned_cart': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === FEATURES ===
            'enable_biometric_login': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_offline_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'offline_cache_size_mb': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 10,
                'max': 500
            }),
            'enable_barcode_scanner': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_ar_preview': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_voice_search': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_shake_to_refresh': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === PERFORMANCE ===
            'image_quality': forms.Select(attrs={'class': 'form-select'}),
            'enable_image_caching': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cache_duration_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 168
            }),
            'enable_lazy_loading': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === DEEP LINKING ===
            'android_package_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'com.store.app'
            }),
            'ios_bundle_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'com.store.app'
            }),
            'app_store_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://apps.apple.com/...'
            }),
            'play_store_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://play.google.com/...'
            }),
            'enable_universal_links': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === ANALYTICS ===
            'enable_app_analytics': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_crash_reporting': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === APP UPDATES ===
            'force_update_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'minimum_app_version': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '1.0.0'
            }),
            'show_update_prompt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_splash_screen_duration(self):
        """Validate splash screen duration range."""
        duration = self.cleaned_data.get('splash_screen_duration')
        if duration and not (1 <= duration <= 5):
            raise ValidationError(
                _("Splash screen duration must be between 1 and 5 seconds."))
        return duration

    def clean_max_bottom_nav_items(self):
        """Validate max bottom nav items range."""
        items = self.cleaned_data.get('max_bottom_nav_items')
        if items and not (3 <= items <= 6):
            raise ValidationError(
                _("Max bottom nav items must be between 3 and 6."))
        return items

    def clean_offline_cache_size_mb(self):
        """Validate offline cache size range."""
        size = self.cleaned_data.get('offline_cache_size_mb')
        if size and not (10 <= size <= 500):
            raise ValidationError(
                _("Offline cache size must be between 10 and 500 MB."))
        return size

    def clean_cache_duration_hours(self):
        """Validate cache duration range."""
        duration = self.cleaned_data.get('cache_duration_hours')
        if duration and not (1 <= duration <= 168):
            raise ValidationError(
                _("Cache duration must be between 1 and 168 hours."))
        return duration

    def clean_primary_color(self):
        """Validate primary color hex format."""
        color = self.cleaned_data.get('primary_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #2563EB)."))
        return color

    def clean_accent_color(self):
        """Validate accent color hex format."""
        color = self.cleaned_data.get('accent_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #F59E0B)."))
        return color

    def clean_background_color(self):
        """Validate background color hex format."""
        color = self.cleaned_data.get('background_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #FFFFFF)."))
        return color

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === Push Notifications Logic ===
        push_enabled = cleaned_data.get('enable_push_notifications')
        firebase_key = cleaned_data.get('firebase_server_key')
        apns_cert = self.cleaned_data.get('apns_certificate')

        if push_enabled and not firebase_key:
            logger.warning(
                "Push notifications enabled but Firebase server key not provided")

        # === Bottom Navigation Logic ===
        max_nav_items = cleaned_data.get('max_bottom_nav_items')
        enabled_tabs = sum([
            cleaned_data.get('show_home_tab', False),
            cleaned_data.get('show_categories_tab', False),
            cleaned_data.get('show_search_tab', False),
            cleaned_data.get('show_cart_tab', False),
            cleaned_data.get('show_account_tab', False),
            cleaned_data.get('show_wishlist_tab', False),
        ])

        if max_nav_items and enabled_tabs > max_nav_items:
            self.add_error(
                'max_bottom_nav_items',
                _("You have %(enabled)s tabs enabled but max is set to %(max)s. "
                  "Please reduce enabled tabs or increase max.") % {
                    'enabled': enabled_tabs,
                    'max': max_nav_items
                }
            )

        # At least 3 tabs should be enabled for proper navigation
        if enabled_tabs < 3:
            self.add_error(
                'show_home_tab',
                _("At least 3 navigation tabs must be enabled.")
            )

        # === Offline Mode Logic ===
        offline_enabled = cleaned_data.get('enable_offline_mode')
        cache_size = cleaned_data.get('offline_cache_size_mb')

        if offline_enabled and not cache_size:
            self.add_error(
                'offline_cache_size_mb',
                _("Offline cache size is required when offline mode is enabled.")
            )

        # === App Updates Logic ===
        force_update = cleaned_data.get('force_update_enabled')
        min_version = cleaned_data.get('minimum_app_version')

        if force_update and not min_version:
            self.add_error(
                'minimum_app_version',
                _("Minimum app version is required when force update is enabled.")
            )

        # === Deep Linking Logic ===
        universal_links = cleaned_data.get('enable_universal_links')
        android_package = cleaned_data.get('android_package_name')
        ios_bundle = cleaned_data.get('ios_bundle_id')

        if universal_links and not (android_package or ios_bundle):
            logger.warning(
                "Universal links enabled but package/bundle IDs not provided")

        # === Color Contrast Warning ===
        primary = cleaned_data.get('primary_color')
        background = cleaned_data.get('background_color')

        if primary and background:
            # Basic contrast check (simplified)
            if primary == background:
                logger.warning(
                    "Primary color and background color are the same - may cause visibility issues")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"MobileAppSettings saved: {instance.app_name} (ID: {instance.id})"
        )
        return instance
