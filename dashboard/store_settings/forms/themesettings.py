import logging
from django import forms
from django.core.validators import validate_comma_separated_integer_list
from ..models import ThemeSettings

logger = logging.getLogger(__name__)


class ThemeSettingsForm(forms.ModelForm):
    """
    Form for managing Tenant Theme Settings.
    Includes custom widgets for color pickers and better UX.
    """
    class Meta:
        model = ThemeSettings
        # Exclude auto-managed fields
        exclude = ['created_at', 'updated_at']
        widgets = {
            # Color Inputs
            'primary_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'secondary_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'accent_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'background_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'secondary_background_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'text_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'secondary_text_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'border_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'success_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'warning_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),
            'error_color': forms.TextInput(attrs={'type': 'color', 'class': 'h-10 w-16 cursor-pointer rounded-lg border border-gray-300 p-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150'}),

            # Selects
            'heading_font': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'body_font': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'spacing_scale': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'shadow_intensity': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'primary_button_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'button_text_transform': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'heading_font_weight': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'body_font_weight': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # Standard Inputs
            'theme_name': forms.TextInput(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150', 'placeholder': 'e.g. Summer Sale Theme'}),
            'custom_font_url': forms.URLInput(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150', 'placeholder': 'https://fonts.googleapis.com/...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'use_shadows': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        # Example of cross-field validation if needed
        # Ensure primary color is not the same as background if contrast is critical
        # (Skipping complex contrast logic for now to keep it robust and simple)
        return cleaned_data

    def save(self, commit=True):
        """
        Override save to handle singleton logic if necessary.
        In this case, standard save works, but we log changes.
        """
        instance = super().save(commit=commit)
        logger.info(
            f"Theme settings updated for tenant schema. Theme ID: {instance.id}")
        return instance
