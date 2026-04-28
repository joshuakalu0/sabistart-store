import logging
import json
from django import forms
from django.core.exceptions import ValidationError
from django.forms import widgets
from ..models import ThemePreset, ThemeSettings

logger = logging.getLogger(__name__)


class JSONEditorWidget(widgets.Textarea):
    """
    Custom widget for JSON field editing with basic validation display.
    """
    template_name = 'widgets/json_editor.html'

    def format_value(self, value):
        if value is None:
            return '{}'
        if isinstance(value, dict):
            return json.dumps(value, indent=4, sort_keys=True)
        return value


class ThemePresetForm(forms.ModelForm):
    """
    Form for creating and editing Theme Presets.
    Includes JSON validation for theme_config field.
    """

    class Meta:
        model = ThemePreset
        fields = [
            'name',
            'description',
            'preview_image',
            'theme_config',
            'style',
            'industry',
            'is_default',
            'is_featured',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'e.g., Minimal Black, Bold Coral'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 3,
                'placeholder': 'What makes this preset unique...'
            }),
            'preview_image': forms.FileInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'accept': 'image/png,image/jpeg,image/webp'
            }),
            'theme_config': JSONEditorWidget(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 font-mono shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'rows': 15,
                'placeholder': '{"primary_color": "#0053db", "heading_font": "inter", ...}'
            }),
            'style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'industry': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
        }

    def clean_theme_config(self):
        """
        Validate that theme_config is valid JSON and contains expected keys.
        """
        data = self.cleaned_data.get('theme_config')

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                raise ValidationError(f"Invalid JSON format: {str(e)}")

        if not isinstance(data, dict):
            raise ValidationError(
                "theme_config must be a JSON object (dictionary)")

        # Validate against ThemeSettings fields (optional but recommended)
        if data:
            valid_fields = set(
                f.name for f in ThemeSettings._meta.get_fields())
            invalid_keys = set(data.keys()) - valid_fields - \
                {'id', 'created_at', 'updated_at'}

            if invalid_keys:
                logger.warning(f"Invalid keys in theme_config: {invalid_keys}")
                # Don't raise error, just warn - allows flexibility

        return data

    def clean_name(self):
        """
        Ensure preset name is unique within the tenant.
        """
        name = self.cleaned_data.get('name')
        instance = self.instance

        queryset = ThemePreset.objects.filter(name__iexact=name)
        if instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        if queryset.exists():
            raise ValidationError("A preset with this name already exists.")

        return name

    def clean(self):
        """
        Cross-field validation.
        """
        cleaned_data = super().clean()

        # Only one default preset per tenant
        is_default = cleaned_data.get('is_default')
        if is_default:
            existing_default = ThemePreset.objects.filter(
                is_default=True
            ).exclude(pk=self.instance.pk if self.instance.pk else None)

            if existing_default.exists():
                raise ValidationError(
                    "Only one preset can be marked as default. "
                    "Please uncheck 'is_default' on the other preset first."
                )

        return cleaned_data

    def save(self, commit=True):
        """
        Handle JSON string conversion if needed.
        """
        instance = super().save(commit=commit)
        logger.info(f"ThemePreset saved: {instance.name} (ID: {instance.id})")
        return instance


class ThemePresetApplyForm(forms.Form):
    """
    Form for applying a preset to the current theme.
    Simple confirmation form.
    """
    preset_id = forms.IntegerField(widget=forms.HiddenInput())
    confirm = forms.BooleanField(
        required=True,
        label="I understand this will overwrite current theme settings"
    )

    def clean_preset_id(self):
        preset_id = self.cleaned_data.get('preset_id')
        try:
            preset = ThemePreset.objects.get(pk=preset_id)
        except ThemePreset.DoesNotExist:
            raise ValidationError("Invalid preset selected.")
        return preset_id
