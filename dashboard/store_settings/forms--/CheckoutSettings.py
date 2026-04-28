import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import CheckoutSettings

logger = logging.getLogger(__name__)


class CheckoutSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Checkout Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = CheckoutSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === CHECKOUT FLOW ===
            'checkout_style': forms.Select(attrs={'class': 'form-select'}),
            'show_breadcrumbs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_order_summary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'order_summary_collapsible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === CUSTOMER INFORMATION ===
            'require_account_creation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_guest_checkout': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_newsletter_signup': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'newsletter_opt_in_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === ADDRESS FIELDS ===
            'require_phone_number': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'require_company_name': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'require_address_line2': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_delivery_instructions': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === SHIPPING ===
            'show_shipping_calculator': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'group_shipping_methods': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === PAYMENT ===
            'show_payment_icons': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_trust_badges': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === CART ===
            'enable_cart_notes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_coupon_codes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_estimated_total': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === CONFIRMATION PAGE ===
            'show_related_products': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_social_sharing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'thank_you_message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Thank you for your order!...',
                'maxlength': 500
            }),

            # === LEGAL ===
            'show_terms_checkbox': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'terms_checkbox_text': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'I agree to the Terms & Conditions',
                'maxlength': 200
            }),
        }

    def clean_thank_you_message(self):
        """Validate thank you message length."""
        message = self.cleaned_data.get('thank_you_message')
        if message and len(message) > 500:
            raise ValidationError(
                _("Thank you message must not exceed 500 characters."))
        return message

    def clean_terms_checkbox_text(self):
        """Validate terms checkbox text length."""
        text = self.cleaned_data.get('terms_checkbox_text')
        if text and len(text) > 200:
            raise ValidationError(
                _("Terms checkbox text must not exceed 200 characters."))
        return text

    def clean(self):
        """Cross-field validation for conflicting settings."""
        cleaned_data = super().clean()

        # === Account Creation vs Guest Checkout ===
        require_account = cleaned_data.get('require_account_creation')
        allow_guest = cleaned_data.get('allow_guest_checkout')

        if require_account and allow_guest:
            self.add_error(
                'require_account_creation',
                _("Cannot require account creation and allow guest checkout at the same time. Please choose one.")
            )
            self.add_error(
                'allow_guest_checkout',
                _("Cannot require account creation and allow guest checkout at the same time. Please choose one.")
            )

        if not require_account and not allow_guest:
            self.add_error(
                'require_account_creation',
                _("You must either require account creation or allow guest checkout.")
            )
            self.add_error(
                'allow_guest_checkout',
                _("You must either require account creation or allow guest checkout.")
            )

        # === Newsletter Logic ===
        show_newsletter = cleaned_data.get('show_newsletter_signup')
        newsletter_default = cleaned_data.get('newsletter_opt_in_default')

        if newsletter_default and not show_newsletter:
            logger.warning(
                "Newsletter opt-in default is set but newsletter signup is disabled")

        # === Terms Checkbox Logic ===
        show_terms = cleaned_data.get('show_terms_checkbox')
        terms_text = cleaned_data.get('terms_checkbox_text')

        if show_terms and not terms_text:
            self.add_error(
                'terms_checkbox_text',
                _("Terms checkbox text is required when terms checkbox is enabled.")
            )

        # === Order Summary Logic ===
        show_summary = cleaned_data.get('show_order_summary')
        summary_collapsible = cleaned_data.get('order_summary_collapsible')

        if summary_collapsible and not show_summary:
            logger.warning(
                "Order summary collapsible is set but order summary is disabled")

        # === Conversion Optimization Warnings ===
        if require_account:
            logger.warning(
                "Requiring account creation may reduce checkout conversion rate")

        if not cleaned_data.get('enable_coupon_codes'):
            logger.info(
                "Coupon codes disabled - may impact promotional campaigns")

        if not cleaned_data.get('show_trust_badges'):
            logger.warning(
                "Trust badges disabled - may impact customer confidence")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"CheckoutSettings saved (checkout_style: {instance.checkout_style}, guest_checkout: {instance.allow_guest_checkout})"
        )
        return instance
