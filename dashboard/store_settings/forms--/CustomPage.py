import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from ..models import CustomPage

logger = logging.getLogger(__name__)


class CustomPageForm(forms.ModelForm):
    """
    Comprehensive form for creating and editing Custom Pages.
    Includes slug auto-generation and SEO validation.
    """

    class Meta:
        model = CustomPage
        fields = [
            'title',
            'slug',
            'content',
            'excerpt',
            'template',
            'show_title',
            'show_breadcrumbs',
            'featured_image',
            'meta_title',
            'meta_description',
            'status',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., About Us, Contact, FAQ'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'about-us (auto-generated from title)'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control font-mono',
                'rows': 15,
                'placeholder': 'Page content (supports HTML)...'
            }),
            'excerpt': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Short description for listings and SEO...',
                'maxlength': 300
            }),
            'template': forms.Select(attrs={'class': 'form-select'}),
            'show_title': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_breadcrumbs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'featured_image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/webp'
            }),
            'meta_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'SEO title (defaults to page title)',
                'maxlength': 70
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'SEO description (max 160 characters)',
                'maxlength': 160
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_slug(self):
        """Validate slug is unique and URL-friendly."""
        slug = self.cleaned_data.get('slug')
        instance = self.instance

        # Auto-generate slug from title if not provided
        if not slug and self.cleaned_data.get('title'):
            slug = slugify(self.cleaned_data.get('title'))

        if slug:
            # Check for uniqueness (exclude current instance if editing)
            queryset = CustomPage.objects.filter(slug=slug)
            if instance.pk:
                queryset = queryset.exclude(pk=instance.pk)

            if queryset.exists():
                raise ValidationError(
                    _("A page with this slug already exists. Please choose a different slug."))

            # Validate slug format
            if not slug.replace('-', '').replace('_', '').isalnum():
                raise
