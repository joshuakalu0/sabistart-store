from django import forms
from .models import Category, Tag, Brand


class CategoryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Safely populate parent choices without causing database errors
        try:
            self.fields['parent'].queryset = Category.objects.filter(
                is_active=True)
            self.fields['parent'].empty_label = "-- No Parent Category --"
        except:
            # If database error, create empty choices
            self.fields['parent'].choices = [('', '-- No Parent Category --')]

    class Meta:
        model = Category
        fields = [
            'name', 'slug', 'parent', 'description', 'image', 'icon',
            'meta_title', 'meta_description', 'meta_keywords', 'canonical_url',
            'display_order', 'featured', 'show_in_menu', 'menu_order',
            'is_active', 'is_visible'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'Enter category name',
                'id': 'id_name'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'category-slug',
                'id': 'id_slug'
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
            'meta_title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'SEO title for this category'
            }),
            'meta_description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'SEO description for search engines...'
            }),
            'meta_keywords': forms.Textarea(attrs={
                'rows': 2,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'keyword1, keyword2, keyword3'
            }),
            'canonical_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'https://example.com/category'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'min': '0'
            }),
            'menu_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'min': '0'
            }),
            'featured': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
            'show_in_menu': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
            'is_visible': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
        }


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = [
            'name', 'slug', 'color', 'icon', 'description',
            'meta_title', 'meta_description', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'Enter tag name',
                'id': 'id_name'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'tag-slug',
                'id': 'id_slug'
            }),
            'color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'w-full h-12 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors cursor-pointer'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'fas fa-tag'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'Describe this tag...'
            }),
            'meta_title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'SEO title for this tag'
            }),
            'meta_description': forms.Textarea(attrs={
                'rows': 2,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'SEO description for search engines...'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
        }


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = [
            'name', 'slug', 'description', 'story', 'logo', 'banner',
            'website', 'email', 'phone',
            'facebook', 'twitter', 'instagram', 'youtube',
            'meta_title', 'meta_description', 'meta_keywords',
            'featured', 'display_order', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'Enter brand name',
                'id': 'id_name'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'brand-slug',
                'id': 'id_slug'
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'Brief description of the brand...'
            }),
            'story': forms.Textarea(attrs={
                'rows': 6,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'Tell the brand story...'
            }),
            'logo': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
            }),
            'banner': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
            }),
            'website': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'https://brandwebsite.com'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'contact@brand.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': '+1 (555) 123-4567'
            }),
            'facebook': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'https://facebook.com/brand'
            }),
            'twitter': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'https://twitter.com/brand'
            }),
            'instagram': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'https://instagram.com/brand'
            }),
            'youtube': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'https://youtube.com/brand'
            }),
            'meta_title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'placeholder': 'SEO title for this brand'
            }),
            'meta_description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'SEO description for search engines...'
            }),
            'meta_keywords': forms.Textarea(attrs={
                'rows': 2,
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none',
                'placeholder': 'keyword1, keyword2, keyword3'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors',
                'min': '0'
            }),
            'featured': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
            }),
        }
