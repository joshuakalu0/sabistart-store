import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..models import BannerSlide

logger = logging.getLogger(__name__)


class BannerSlideForm(forms.ModelForm):
    """
    Comprehensive form for creating and editing Banner Slides.
    Includes image validation and date range checks.
    """

    class Meta:
        model = BannerSlide
        fields = [
            'title',
            'subtitle',
            'description',
            'image_desktop',
            'image_mobile',
            'text_position',
            'text_color',
            'overlay_opacity',
            'cta_text',
            'cta_link',
            'cta_style',
            'show_cta',
            'is_active',
            'display_order',
            'start_date',
            'end_date',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'e.g., Summer Sale 2024'
            }),
            'subtitle': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Supporting text below title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 3,
                'placeholder': 'Additional description text...',
                'maxlength': 300
            }),
            'image_desktop': forms.FileInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'accept': 'image/png,image/jpeg,image/webp'
            }),
            'image_mobile': forms.FileInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'accept': 'image/png,image/jpeg,image/webp'
            }),
            'text_position': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'text_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'overlay_opacity': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 0,
                'max': 100
            }),
            'cta_text': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Shop Now'
            }),
            'cta_link': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': '/collections/summer or https://...'
            }),
            'cta_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_cta': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 0
            }),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'datetime-local'
            }),
            'end_date': forms.DateTimeInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'datetime-local'
            }),
        }

    def clean_overlay_opacity(self):
        """Validate overlay opacity range."""
        opacity = self.cleaned_data.get('overlay_opacity')
        if opacity and not (0 <= opacity <= 100):
            raise ValidationError(
                _("Overlay opacity must be between 0 and 100."))
        return opacity

    def clean_cta_text(self):
        """Validate CTA text length."""
        text = self.cleaned_data.get('cta_text')
        if text and len(text) > 50:
            raise ValidationError(_("CTA text must not exceed 50 characters."))
        return text

    def clean_description(self):
        """Validate description length."""
        desc = self.cleaned_data.get('description')
        if desc and len(desc) > 300:
            raise ValidationError(
                _("Description must not exceed 300 characters."))
        return desc

    def clean(self):
        """Cross-field validation for date range and CTA settings."""
        cleaned_data = super().clean()

        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        # Validate date range
        if start_date and end_date:
            if start_date >= end_date:
                self.add_error(
                    'end_date',
                    _("End date must be after start date.")
                )

        # Warn if CTA is shown but no link provided
        show_cta = cleaned_data.get('show_cta')
        cta_link = cleaned_data.get('cta_link')

        if show_cta and not cta_link:
            logger.warning(
                f"CTA is shown but no link provided for banner: {cleaned_data.get('title')}")

        # Warn if mobile image not provided
        image_mobile = cleaned_data.get('image_mobile')
        image_desktop = cleaned_data.get('image_desktop')

        if not image_mobile and image_desktop:
            logger.info(
                f"Mobile image not provided for banner: {cleaned_data.get('title')} - desktop image will be used")

        # Validate CTA text when CTA is shown
        cta_text = cleaned_data.get('cta_text')

        if show_cta and not cta_text:
            self.add_error(
                'cta_text',
                _("CTA text is required when CTA button is shown.")
            )

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"BannerSlide saved: {instance.title} (order: {instance.display_order}, active: {instance.is_active})"
        )
        return instance


class BannerSlideBulkActionForm(forms.Form):
    """
    Form for bulk actions on multiple banner slides.
    """
    action = forms.ChoiceField(
        choices=[
            ('activate', 'Activate Selected'),
            ('deactivate', 'Deactivate Selected'),
            ('delete', 'Delete Selected'),
        ],
        widget=forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'})
    )
    slide_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
