import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import EmailTemplateSettings

logger = logging.getLogger(__name__)


class EmailTemplateSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Email Template Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = EmailTemplateSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === BRANDING ===
            'logo': forms.FileInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'accept': 'image/png,image/jpeg,image/svg+xml'
            }),
            'accent_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'background_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'content_background_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'text_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),

            # === HEADER ===
            'header_text': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'e.g., Thank you for your order!'
            }),
            'show_social_links_in_header': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === FOOTER ===
            'footer_text': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 4,
                'placeholder': 'Footer message (supports HTML)...'
            }),
            'show_contact_info': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_social_links_in_footer': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_unsubscribe_link': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === CONTENT ===
            'button_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'button_border_radius': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 0,
                'max': 50
            }),

            # === TYPOGRAPHY ===
            'font_family': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # === SPECIFIC EMAIL SETTINGS ===
            'order_confirmation_custom_message': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 3,
                'placeholder': 'Additional message for order confirmation...'
            }),
            'shipping_notification_custom_message': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 3,
                'placeholder': 'Additional message for shipping notification...'
            }),
        }

    def clean_accent_color(self):
        """Validate accent color hex format."""
        color = self.cleaned_data.get('accent_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #2563EB)."))
        return color

    def clean_background_color(self):
        """Validate background color hex format."""
        color = self.cleaned_data.get('background_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #F3F4F6)."))
        return color

    def clean_content_background_color(self):
        """Validate content background color hex format."""
        color = self.cleaned_data.get('content_background_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #FFFFFF)."))
        return color

    def clean_text_color(self):
        """Validate text color hex format."""
        color = self.cleaned_data.get('text_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #1F2937)."))
        return color

    def clean_button_border_radius(self):
        """Validate button border radius range."""
        radius = self.cleaned_data.get('button_border_radius')
        if radius and not (0 <= radius <= 50):
            raise ValidationError(
                _("Button border radius must be between 0 and 50."))
        return radius

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === Color Contrast Warnings ===
        content_bg = cleaned_data.get('content_background_color')
        text_color = cleaned_data.get('text_color')

        if content_bg and text_color and content_bg == text_color:
            self.add_error(
                'text_color',
                _("Text color and content background color are the same - this will cause readability issues.")
            )

        bg_color = cleaned_data.get('background_color')
        content_bg = cleaned_data.get('content_background_color')

        if bg_color and content_bg and bg_color == content_bg:
            logger.warning(
                "Background color and content background color are the same - content may not stand out")

        # === Unsubscribe Link Warning ===
        show_unsubscribe = cleaned_data.get('show_unsubscribe_link')

        if not show_unsubscribe:
            logger.warning(
                "Unsubscribe link is disabled - this may violate email marketing regulations (GDPR, CAN-SPAM)")

        # === Footer Text HTML Validation (Basic) ===
        footer_text = cleaned_data.get('footer_text')

        if footer_text:
            # Basic check for unclosed tags (simplified)
            if footer_text.count('<') != footer_text.count('>'):
                logger.warning("Footer text may have unclosed HTML tags")

        # === Social Links Logic ===
        show_social_header = cleaned_data.get('show_social_links_in_header')
        show_social_footer = cleaned_data.get('show_social_links_in_footer')

        if not show_social_header and not show_social_footer:
            logger.info("Social links disabled in both header and footer")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"EmailTemplateSettings saved (ID: {instance.id})"
        )
        return instance
