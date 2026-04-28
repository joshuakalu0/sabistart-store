import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import PopupSettings

logger = logging.getLogger(__name__)


class PopupSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Popup Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = PopupSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === NEWSLETTER POPUP ===
            'enable_newsletter_popup': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'popup_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Join Our Newsletter'
            }),
            'popup_description': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 3,
                'placeholder': 'Subscribe to get special offers...'
            }),
            'popup_image': forms.FileInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'accept': 'image/png,image/jpeg,image/webp'
            }),
            'popup_button_text': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Subscribe'
            }),
            'show_discount_code': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'discount_code_text': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': "Get 10% off your first order!"
            }),

            # === TRIGGER SETTINGS ===
            'trigger_type': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'trigger_delay_seconds': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 0,
                'max': 60
            }),
            'trigger_scroll_percentage': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 0,
                'max': 100
            }),

            # === FREQUENCY ===
            'show_once_per_session': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_once_per_days': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 365
            }),
            'show_to_subscribers': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_on_mobile': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === APPEARANCE ===
            'popup_position': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'popup_size': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'overlay_opacity': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 0,
                'max': 100
            }),
            'popup_animation': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'enable_close_button': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'close_on_overlay_click': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === COOKIE CONSENT ===
            'enable_cookie_consent': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cookie_message': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 3
            }),
            'cookie_button_text': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Accept'
            }),
            'cookie_policy_url': forms.URLInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'https://yoursite.com/cookie-policy'
            }),
            'cookie_banner_position': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_cookie_settings': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === PROMOTIONAL BANNER ===
            'enable_promo_banner': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'promo_banner_text': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Free shipping on orders over $50!'
            }),
            'promo_banner_link': forms.URLInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'
            }),
            'promo_banner_background': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'promo_banner_text_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'promo_banner_position': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'promo_banner_dismissible': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'promo_banner_sticky': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === EXIT INTENT ===
            'enable_exit_intent': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'exit_intent_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Wait! Before you go...'
            }),
            'exit_intent_message': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 3
            }),
            'exit_intent_offer': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': '10% off your first order'
            }),

            # === A/B TESTING ===
            'enable_ab_testing': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'variant_a_title': forms.TextInput(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'variant_b_title': forms.TextInput(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
        }

    def clean_trigger_delay_seconds(self):
        """Validate trigger delay range."""
        delay = self.cleaned_data.get('trigger_delay_seconds')
        if delay and not (0 <= delay <= 60):
            raise ValidationError(
                _("Trigger delay must be between 0 and 60 seconds."))
        return delay

    def clean_trigger_scroll_percentage(self):
        """Validate scroll percentage range."""
        percentage = self.cleaned_data.get('trigger_scroll_percentage')
        if percentage and not (0 <= percentage <= 100):
            raise ValidationError(
                _("Scroll percentage must be between 0 and 100."))
        return percentage

    def clean_show_once_per_days(self):
        """Validate show once per days range."""
        days = self.cleaned_data.get('show_once_per_days')
        if days and not (1 <= days <= 365):
            raise ValidationError(_("Days must be between 1 and 365."))
        return days

    def clean_overlay_opacity(self):
        """Validate overlay opacity range."""
        opacity = self.cleaned_data.get('overlay_opacity')
        if opacity and not (0 <= opacity <= 100):
            raise ValidationError(
                _("Overlay opacity must be between 0 and 100."))
        return opacity

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === Newsletter Popup Logic ===
        newsletter_enabled = cleaned_data.get('enable_newsletter_popup')
        discount_enabled = cleaned_data.get('show_discount_code')
        discount_text = cleaned_data.get('discount_code_text')

        if not newsletter_enabled:
            logger.info(
                "Newsletter popup disabled - related settings will be ignored")

        if newsletter_enabled and discount_enabled and not discount_text:
            self.add_error(
                'discount_code_text',
                _("Discount code text is required when offering discount.")
            )

        # === Trigger Type Logic ===
        trigger_type = cleaned_data.get('trigger_type')
        delay = cleaned_data.get('trigger_delay_seconds')
        scroll_pct = cleaned_data.get('trigger_scroll_percentage')

        if trigger_type == 'time' and delay is None:
            self.add_error(
                'trigger_delay_seconds',
                _("Delay is required for time-based trigger.")
            )

        if trigger_type == 'scroll' and scroll_pct is None:
            self.add_error(
                'trigger_scroll_percentage',
                _("Scroll percentage is required for scroll-based trigger.")
            )

        # === Exit Intent Logic ===
        exit_intent_enabled = cleaned_data.get('enable_exit_intent')
        exit_title = cleaned_data.get('exit_intent_title')
        exit_message = cleaned_data.get('exit_intent_message')

        if exit_intent_enabled and not exit_title:
            self.add_error(
                'exit_intent_title',
                _("Exit intent title is required when exit intent is enabled.")
            )

        # === Cookie Consent Logic ===
        cookie_enabled = cleaned_data.get('enable_cookie_consent')
        cookie_policy_url = cleaned_data.get('cookie_policy_url')
        show_settings = cleaned_data.get('show_cookie_settings')

        if cookie_enabled and not cookie_policy_url:
            logger.warning(
                "Cookie consent enabled but no policy URL provided - may have compliance issues")

        # === Promo Banner Logic ===
        promo_enabled = cleaned_data.get('enable_promo_banner')
        promo_text = cleaned_data.get('promo_banner_text')

        if promo_enabled and not promo_text:
            self.add_error(
                'promo_banner_text',
                _("Promo banner text is required when banner is enabled.")
            )

        # === A/B Testing Logic ===
        ab_enabled = cleaned_data.get('enable_ab_testing')
        variant_a = cleaned_data.get('variant_a_title')
        variant_b = cleaned_data.get('variant_b_title')

        if ab_enabled and not (variant_a and variant_b):
            self.add_error(
                'enable_ab_testing',
                _("Both variant A and B titles are required for A/B testing.")
            )

        # === Frequency Logic ===
        once_session = cleaned_data.get('show_once_per_session')
        once_days = cleaned_data.get('show_once_per_days')

        if once_session and once_days:
            logger.info(
                "Both session and day-based frequency set - day setting will take precedence")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"PopupSettings saved (tenant schema: {instance._meta.db_table})"
        )
        return instance
