from django import forms
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from .models import Category, Tag, Brand


class CategoryForm(forms.ModelForm):
    slug = forms.CharField(required=False, widget=forms.HiddenInput())
    display_order = forms.IntegerField(required=False, widget=forms.HiddenInput(), initial=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Safely populate parent choices without causing database errors
        try:
            self.fields['parent'].queryset = Category.objects.filter(
                is_active=True)
            self.fields['parent'].empty_label = "-- No Parent Category --"
        except Exception:
            self.fields['parent'].choices = [('', '-- No Parent Category --')]

    class Meta:
        model = Category
        fields = [
            'name', 'slug', 'parent', 'description', 'image', 'icon',
            'display_order', 'is_active', 'is_visible'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'Enter category name',
                'id': 'id_name'
            }),
            'parent': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors'
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'Describe this category...'
            }),
            'image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'fas fa-icon-name'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
            'is_visible': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        slug = cleaned_data.get('slug')
        name = cleaned_data.get('name')
        if not slug and name:
            base = slugify(name) or 'category'
            suffix = get_random_string(6, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')
            unique_slug = f"{base}-{suffix}"
            qs = Category.objects.filter(slug=unique_slug)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            while qs.exists():
                suffix = get_random_string(6, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')
                unique_slug = f"{base}-{suffix}"
                qs = Category.objects.filter(slug=unique_slug)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
            cleaned_data['slug'] = unique_slug
        return cleaned_data


class TagForm(forms.ModelForm):
    slug = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Tag
        fields = ['name', 'slug', 'color', 'icon', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'Enter tag name',
                'id': 'id_name'
            }),
            'color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'w-16 h-10 border border-slate-300 dark:border-slate-600 rounded-lg cursor-pointer'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'fas fa-tag'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'Brief description of this tag...'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        slug = cleaned_data.get('slug')
        name = cleaned_data.get('name')
        if not slug and name:
            base = slugify(name) or 'tag'
            suffix = get_random_string(6, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')
            cleaned_data['slug'] = f"{base}-{suffix}"
        return cleaned_data


class BrandForm(forms.ModelForm):
    """
    Brand form: Only brand name and image (logo) are required/displayed.
    Slug is automatically generated at the backend with a random suffix.
    """
    slug = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Brand
        fields = ['name', 'logo', 'slug']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'Enter brand name',
                'id': 'id_name'
            }),
            'logo': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        slug = cleaned_data.get('slug')
        name = cleaned_data.get('name')
        if not slug and name:
            base = slugify(name) or 'brand'
            suffix = get_random_string(6, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')
            unique_slug = f"{base}-{suffix}"
            qs = Brand.objects.filter(slug=unique_slug)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            while qs.exists():
                suffix = get_random_string(6, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')
                unique_slug = f"{base}-{suffix}"
                qs = Brand.objects.filter(slug=unique_slug)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
            cleaned_data['slug'] = unique_slug
        return cleaned_data
