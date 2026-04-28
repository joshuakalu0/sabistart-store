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
            'primary_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'secondary_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'accent_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'background_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'secondary_background_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'text_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'secondary_text_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'border_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'success_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'warning_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),
            'error_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control-color'}),

            # Selects
            'heading_font': forms.Select(attrs={'class': 'form-select'}),
            'body_font': forms.Select(attrs={'class': 'form-select'}),
            'spacing_scale': forms.Select(attrs={'class': 'form-select'}),
            'shadow_intensity': forms.Select(attrs={'class': 'form-select'}),
            'primary_button_style': forms.Select(attrs={'class': 'form-select'}),
            'button_text_transform': forms.Select(attrs={'class': 'form-select'}),
            'heading_font_weight': forms.Select(attrs={'class': 'form-select'}),
            'body_font_weight': forms.Select(attrs={'class': 'form-select'}),

            # Standard Inputs
            'theme_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Summer Sale Theme'}),
            'custom_font_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://fonts.googleapis.com/...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'use_shadows': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
