import logging
import json
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import FooterSettings

logger = logging.getLogger(__name__)


class FooterSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Footer Settings.
    Organized into logical sections for better UX.
    """

    # JSON Field for accepted payments - using a text area for simplicity
    accepted_payments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control font-mono',
            'rows': 3,
            'placeholder': "visa, mastercard, paypal, apple_pay, google_pay"
        }),
        help_text="Comma-separated list of payment methods"
    )

    class Meta:
        model = FooterSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === LAYOUT ===
            'layout': forms.Select(attrs={'class': 'form-select'}),
            'background_color': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'text_color': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),

            # === CONTENT ===
            'show_logo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'about_text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Quality products since 2020'
            }),
            'copyright_text': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '© 2024 YourStore. All rights reserved.'
            }),

            # === NEWSLETTER ===
            'show_newsletter': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'newsletter_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subscribe to our newsletter'
            }),
            'newsletter_description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Get the latest updates on new products and upcoming sales'
            }),

            # === PAYMENT METHODS ===
            'show_payment_icons': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === SOCIAL MEDIA ===
            'show_social_links': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'social_links_style': forms.Select(attrs={'class': 'form-select'}),

            # === TRUST BADGES ===
            'show_trust_badges': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'trust_badge_1': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/svg+xml'
            }),
            'trust_badge_2': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/svg+xml'
            }),
            'trust_badge_3': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/svg+xml'
            }),

            # === LEGAL LINKS ===
            'show_legal_links': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_background_color(self):
        """Validate background color hex format."""
        color = self.cleaned_data.get('background_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #1F2937)."))
        return color

    def clean_text_color(self):
        """Validate text color hex format."""
        color = self.cleaned_data.get('text_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #FFFFFF)."))
        return color

    def clean_accepted_payments(self):
        """Validate and convert accepted payments from comma-separated string to list."""
        payments_str = self.cleaned_data.get('accepted_payments', '')

        if not payments_str:
            return []

        # Parse comma-separated string
        payments = [payment.strip().lower()
                    for payment in payments_str.split(',') if payment.strip()]

        # Validate payment method names (optional - can be customized)
        valid_payments = ['visa', 'mastercard', 'american_express', 'discover', 'paypal',
                          'apple_pay', 'google_pay', 'shop_pay', 'klarna', 'afterpay',
                          'stripe', 'square', 'bitcoin', 'ethereum']

        invalid_payments = [p for p in payments if p not in valid_payments]

        if invalid_payments:
            logger.warning(f"Unknown payment methods: {invalid_payments}")
            # Don't raise error, just warn - allows flexibility for custom payment methods

        return payments

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === Newsletter Logic ===
        show_newsletter = cleaned_data.get('show_newsletter')
        newsletter_title = cleaned_data.get('newsletter_title')

        if show_newsletter and not newsletter_title:
            self.add_error(
                'newsletter_title',
                _("Newsletter title is required when newsletter signup is enabled.")
            )

        # === Trust Badges Logic ===
        show_trust_badges = cleaned_data.get('show_trust_badges')

        if show_trust_badges:
            # At least one badge should be uploaded
            badge_1 = self.cleaned_data.get('trust_badge_1')
            badge_2 = self.cleaned_data.get('trust_badge_2')
            badge_3 = self.cleaned_data.get('trust_badge_3')

            # Check if instance has existing badges
            if self.instance.pk:
                has_existing = (
                    self.instance.trust_badge_1 or
                    self.instance.trust_badge_2 or
                    self.instance.trust_badge_3
                )

                if not has_existing and not badge_1 and not badge_2 and not badge_3:
                    self.add_error(
                        'show_trust_badges',
                        _("At least one trust badge image is required when trust badges are enabled.")
                    )

        # === Color Contrast Warning ===
        bg_color = cleaned_data.get('background_color')
        txt_color = cleaned_data.get('text_color')

        if bg_color and txt_color and bg_color == txt_color:
            self.add_error(
                'text_color',
                _("Text color and background color are the same - this will cause visibility issues.")
            )

        # === Social Links Logic ===
        show_social = cleaned_data.get('show_social_links')

        if not show_social:
            logger.info(
                "Social links disabled - social links style setting will be ignored")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=False)

        # Convert accepted payments from string to list for JSONField
        payments_str = self.cleaned_data.get('accepted_payments', '')
        if payments_str:
            instance.accepted_payments = [
                payment.strip().lower() for payment in payments_str.split(',') if payment.strip()
            ]
        else:
            instance.accepted_payments = []

        if commit:
            instance.save()
            logger.info(
                f"FooterSettings saved: {instance.layout} (ID: {instance.id})"
            )

        return instance
