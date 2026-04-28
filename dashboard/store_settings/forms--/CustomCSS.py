import logging
import re
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import CustomCSS

logger = logging.getLogger(__name__)


class CustomCSSForm(forms.ModelForm):
    """
    Comprehensive form for creating and editing Custom CSS snippets.
    Includes CSS validation and security checks.
    """

    class Meta:
        model = CustomCSS
        fields = [
            'name',
            'css_code',
            'description',
            'apply_to',
            'custom_pages',
            'apply_to_mobile',
            'apply_to_tablet',
            'apply_to_desktop',
            'is_active',
            'load_order',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Header tweaks, Custom buttons'
            }),
            'css_code': forms.Textarea(attrs={
                'class': 'form-control font-mono',
                'rows': 15,
                'placeholder': '/* Enter your CSS code here (without <style> tags) */\n.example {\n    color: #ff0000;\n}',
                'spellcheck': 'false'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe what this CSS does...',
                'maxlength': 500
            }),
            'apply_to': forms.Select(attrs={'class': 'form-select'}),
            'custom_pages': forms.Textarea(attrs={
                'class': 'form-control font-mono',
                'rows': 3,
                'placeholder': 'Comma-separated page IDs: 1, 2, 3',
                'style': 'display: none;'  # Hidden, managed via JavaScript
            }),
            'apply_to_mobile': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'apply_to_tablet': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'apply_to_desktop': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'load_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': -1000,
                'max': 1000
            }),
        }

    def clean_name(self):
        """Validate CSS snippet name is unique within tenant."""
        name = self.cleaned_data.get('name')
        instance = self.instance

        # Check for duplicate names (case-insensitive)
        queryset = CustomCSS.objects.filter(name__iexact=name)
        if instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        if queryset.exists():
            raise ValidationError(
                _("A CSS snippet with this name already exists. Please choose a different name."))

        return name

    def clean_css_code(self):
        """Validate CSS code for security and syntax."""
        css_code = self.cleaned_data.get('css_code')

        if not css_code or not css_code.strip():
            raise ValidationError(_("CSS code is required."))

        # Security checks
        dangerous_patterns = [
            (r'<script', 'Script tags are not allowed in CSS'),
            (r'javascript:', 'JavaScript URLs are not allowed in CSS'),
            (r'expression\s*\(', 'CSS expressions are not allowed'),
            (r'@import', '@import rules are not allowed for security'),
            (r'behavior\s*:', 'IE behaviors are not allowed'),
        ]

        for pattern, message in dangerous_patterns:
            if re.search(pattern, css_code, re.IGNORECASE):
                raise ValidationError(
                    _(f"Security violation: {message}. Please remove this from your CSS code."))

        # Basic syntax validation (check for balanced braces)
        open_braces = css_code.count('{')
        close_braces = css_code.count('}')

        if open_braces != close_braces:
            logger.warning(
                f"CSS code may have unbalanced braces: {open_braces} open, {close_braces} close")
            # Don't raise error, just warn - CSS can have edge cases

        # Warn about very large CSS
        if len(css_code) > 50000:
            logger.warning(
                f"Large CSS snippet ({len(css_code)} chars) - may impact performance")

        return css_code

    def clean_custom_pages(self):
        """Validate and convert custom pages from comma-separated string to list."""
        custom_pages_str = self.cleaned_data.get('custom_pages', '')
        apply_to = self.cleaned_data.get('apply_to')

        if apply_to != 'custom':
            return []

        if not custom_pages_str:
            raise ValidationError(
                _("Custom page IDs are required when applying to custom pages."))

        # Parse comma-separated string
        try:
            pages = [int(page.strip())
                     for page in custom_pages_str.split(',') if page.strip()]
        except ValueError:
            raise ValidationError(_("Custom page IDs must be valid integers."))

        if not pages:
            raise ValidationError(
                _("At least one custom page ID is required."))

        return pages

    def clean_load_order(self):
        """Validate load order range."""
        load_order = self.cleaned_data.get('load_order')
        if load_order and not (-1000 <= load_order <= 1000):
            raise ValidationError(
                _("Load order must be between -1000 and 1000."))
        return load_order

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        apply_to = cleaned_data.get('apply_to')
        custom_pages = cleaned_data.get('custom_pages')

        # Validate custom pages only when apply_to is 'custom'
        if apply_to == 'custom' and not custom_pages:
            self.add_error(
                'custom_pages',
                _("Custom page IDs are required when applying to custom pages.")
            )

        # Warn if no devices selected
        mobile = cleaned_data.get('apply_to_mobile')
        tablet = cleaned_data.get('apply_to_tablet')
        desktop = cleaned_data.get('apply_to_desktop')

        if not (mobile or tablet or desktop):
            self.add_error(
                'apply_to_mobile',
                _("CSS must be applied to at least one device type.")
            )

        # Warn about high load order
        load_order = cleaned_data.get('load_order')
        if load_order and load_order > 500:
            logger.warning(
                f"High load order ({load_order}) may override important theme styles")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"CustomCSS saved: {instance.name} (load_order: {instance.load_order}, active: {instance.is_active})"
        )
        return instance


class CustomCSSBulkActionForm(forms.Form):
    """
    Form for bulk actions on multiple CSS snippets.
    """
    action = forms.ChoiceField(
        choices=[
            ('activate', 'Activate Selected'),
            ('deactivate', 'Deactivate Selected'),
            ('delete', 'Delete Selected'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    css_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
