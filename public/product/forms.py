from django import forms
from django.forms import inlineformset_factory
from .models import (
    AttributeGroup, Attribute, AttributeValue, Product, ProductImage,
    ProductVideo,  ProductAttributeValue, ProductVariant, VariantImage
)
from public.category.models import Category, Tag, Brand
import json

# Base widget classes
BASE_INPUT = 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors'
BASE_SELECT = 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors'
BASE_TEXTAREA = 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors resize-none'
BASE_CHECKBOX = 'w-5 h-5 text-blue-600 bg-slate-100 border-slate-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-slate-800 focus:ring-2 dark:bg-slate-700 dark:border-slate-600'
BASE_FILE = 'w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-slate-700 dark:text-white transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'


class AttributeGroupForm(forms.ModelForm):
    class Meta:
        model = AttributeGroup
        fields = '__all__'
        exclude = ['created_at', 'updated_at']
        widgets = {
            'name': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Enter group name', 'id': 'id_name'}),
            'slug': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'group-slug', 'id': 'id_slug'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': BASE_TEXTAREA, 'placeholder': 'Group description...'}),
            'display_order': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
        }


class AttributeForm(forms.ModelForm):
    class Meta:
        model = Attribute
        fields = '__all__'
        exclude = ['created_at', 'updated_at']
        widgets = {
            'name': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Enter attribute name', 'id': 'id_name'}),
            'slug': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'attribute-slug', 'id': 'id_slug'}),
            'attribute_type': forms.Select(attrs={'class': BASE_SELECT}),
            'group': forms.Select(attrs={'class': BASE_SELECT, 'empty_label': 'Select Group'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': BASE_TEXTAREA, 'placeholder': 'Attribute description...'}),
            'help_text': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Help text for users'}),
            'unit': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'e.g., cm, kg, etc.'}),
            'is_required': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_unique': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'min_value': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.0001'}),
            'max_value': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.0001'}),
            'regex_pattern': forms.TextInput(attrs={'class': BASE_INPUT + ' font-mono text-sm', 'placeholder': '^[A-Za-z0-9]+$'}),
            'is_variant_option': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_filterable': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_searchable': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_comparable': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'display_order': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
            'is_visible_on_front': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
        }


class AttributeValueForm(forms.ModelForm):
    class Meta:
        model = AttributeValue
        fields = '__all__'
        exclude = ['created_at']
        widgets = {
            'attribute': forms.Select(attrs={'class': BASE_SELECT}),
            'value': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Enter value'}),
            'slug': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'value-slug', 'id': 'id_slug'}),
            'color_hex': forms.TextInput(attrs={'type': 'color', 'class': 'w-full h-12 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 cursor-pointer'}),
            'image': forms.ClearableFileInput(attrs={'class': BASE_FILE}),
            'swatch': forms.ClearableFileInput(attrs={'class': BASE_FILE}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': BASE_TEXTAREA, 'placeholder': 'Value description...'}),
            'extra_price': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'display_order': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
        }


class ProductForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['categories'].queryset = Category.objects.all()
            self.fields['tags'].queryset = Tag.objects.all()
            self.fields['brand'].queryset = Brand.objects.all()
        except:
            pass

        # Make only name and slug required for multi-step form
        for field_name, field in self.fields.items():
            if field_name not in ['name', 'slug']:
                field.required = False

    class Meta:
        model = Product
        fields = '__all__'
        exclude = ['id', 'created_at', 'updated_at', 'published_at', 'view_count',
                   'sales_count', 'average_rating', 'rating_count', 'review_count']
        widgets = {
            # Basic Info
            'name': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Enter product name', 'id': 'id_name'}),
            'slug': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'product-slug', 'id': 'id_slug'}),
            'sku': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'SKU-001'}),
            'product_type': forms.Select(attrs={'class': BASE_SELECT}),
            'categories': forms.SelectMultiple(attrs={'class': BASE_SELECT, 'size': '4'}),
            'tags': forms.SelectMultiple(attrs={'class': BASE_SELECT, 'size': '4'}),
            'brand': forms.Select(attrs={'class': BASE_SELECT, 'empty_label': 'Select Brand'}),

            # Content
            'short_description': forms.Textarea(attrs={'rows': 3, 'class': BASE_TEXTAREA, 'placeholder': 'Brief product description...'}),
            'description': forms.Textarea(attrs={'rows': 8, 'class': BASE_TEXTAREA, 'placeholder': 'Detailed product description...'}),
            'specifications': forms.Textarea(attrs={'rows': 6, 'class': BASE_TEXTAREA + ' font-mono text-sm', 'placeholder': '{"dimension": "10x20x30 cm", "weight": "2.5 kg"}'}),
            'features': forms.Textarea(attrs={'rows': 6, 'class': BASE_TEXTAREA + ' font-mono text-sm', 'placeholder': '["Feature 1", "Feature 2", "Feature 3"]'}),

            # Pricing
            'price': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'compare_at_price': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'cost_price': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'tax_class': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'standard'}),
            'tax_status': forms.Select(attrs={'class': BASE_SELECT}),

            # Inventory
            'manage_stock': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'stock_quantity': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
            'stock_status': forms.Select(attrs={'class': BASE_SELECT}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0', 'value': '5'}),
            'backorders_allowed': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),

            # Shipping
            'requires_shipping': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'weight': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.001', 'min': '0', 'placeholder': 'Weight in kg'}),
            'length': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0', 'placeholder': 'Length in cm'}),
            'width': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0', 'placeholder': 'Width in cm'}),
            'height': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0', 'placeholder': 'Height in cm'}),
            'shipping_class': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'standard'}),

            # Digital Products
            'is_downloadable': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'download_limit': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '1', 'placeholder': 'Max downloads per purchase'}),
            'download_expiry': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '1', 'placeholder': 'Days until download expires'}),

            # Subscription
            'subscription_period': forms.Select(attrs={'class': BASE_SELECT}),
            'subscription_length': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '1', 'placeholder': 'Number of periods'}),
            'trial_period': forms.Select(attrs={'class': BASE_SELECT}),
            'trial_length': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '1'}),

            # SEO
            'meta_title': forms.TextInput(attrs={'class': BASE_INPUT, 'maxlength': '255', 'placeholder': 'SEO title for this product'}),
            'meta_description': forms.Textarea(attrs={'rows': 3, 'class': BASE_TEXTAREA, 'maxlength': '500', 'placeholder': 'SEO description for search engines...'}),
            'meta_keywords': forms.Textarea(attrs={'rows': 2, 'class': BASE_TEXTAREA, 'placeholder': 'keyword1, keyword2, keyword3'}),
            'canonical_url': forms.URLInput(attrs={'class': BASE_INPUT, 'placeholder': 'https://example.com/product'}),
            'focus_keyword': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'main keyword'}),

            # Reviews & Ratings
            'enable_reviews': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),

            # Status & Visibility
            'status': forms.Select(attrs={'class': BASE_SELECT}),
            'is_active': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_featured': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_bestseller': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_new': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_on_sale': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'catalog_visibility': forms.Select(attrs={'class': BASE_SELECT}),
            'sold_individually': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'min_purchase_quantity': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '1', 'value': '1'}),
            'max_purchase_quantity': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '1'}),

            # Dates
            'available_from': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': BASE_INPUT}),
            'available_until': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': BASE_INPUT}),
        }

    def clean_specifications(self):
        data = self.cleaned_data.get('specifications')
        if data:
            try:
                parsed = json.loads(data) if isinstance(data, str) else data
                if not isinstance(parsed, dict):
                    raise forms.ValidationError(
                        "Specifications must be a JSON object")
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format")
        return data

    def clean_features(self):
        data = self.cleaned_data.get('features')
        if data:
            try:
                parsed = json.loads(data) if isinstance(data, str) else data
                if not isinstance(parsed, list):
                    raise forms.ValidationError(
                        "Features must be a JSON array")
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format")
        return data


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = '__all__'
        exclude = ['created_at']
        widgets = {
            'product': forms.Select(attrs={'class': BASE_SELECT}),
            'image': forms.ClearableFileInput(attrs={'class': BASE_FILE}),
            'thumbnail': forms.ClearableFileInput(attrs={'class': BASE_FILE}),
            'alt_text': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Alt text for accessibility'}),
            'title': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Image title'}),
            'caption': forms.Textarea(attrs={'rows': 2, 'class': BASE_TEXTAREA, 'placeholder': 'Image caption...'}),
            'is_primary': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'display_order': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
            'is_zoom_enabled': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'show_in_gallery': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
        }


class ProductVideoForm(forms.ModelForm):
    class Meta:
        model = ProductVideo
        fields = '__all__'
        exclude = ['created_at']
        widgets = {
            'product': forms.Select(attrs={'class': BASE_SELECT}),
            'video_type': forms.Select(attrs={'class': BASE_SELECT}),
            'video_url': forms.URLInput(attrs={'class': BASE_INPUT, 'placeholder': 'https://youtube.com/watch?v=...'}),
            'video_id': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'YouTube/Vimeo video ID'}),
            'video_file': forms.ClearableFileInput(attrs={'class': BASE_FILE}),
            'title': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Video title'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': BASE_TEXTAREA, 'placeholder': 'Video description...'}),
            'thumbnail': forms.ClearableFileInput(attrs={'class': BASE_FILE}),
            'display_order': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
            'is_featured': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
        }


# class ProductDocumentForm(forms.ModelForm):
#     class Meta:
#         model = ProductDocument
#         fields = '__all__'
#         exclude = ['created_at', 'file_size']
#         widgets = {
#             'product': forms.Select(attrs={'class': BASE_SELECT}),
#             'title': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Document title'}),
#             'description': forms.Textarea(attrs={'rows': 3, 'class': BASE_TEXTAREA, 'placeholder': 'Document description...'}),
#             'file': forms.ClearableFileInput(attrs={'class': BASE_FILE}),
#             'document_type': forms.Select(attrs={'class': BASE_SELECT}),
#             'is_downloadable': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
#             'requires_login': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
#             'display_order': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
#         }


class ProductAttributeValueForm(forms.ModelForm):
    class Meta:
        model = ProductAttributeValue
        fields = '__all__'
        widgets = {
            'product': forms.Select(attrs={'class': BASE_SELECT}),
            'attribute': forms.Select(attrs={'class': BASE_SELECT}),
            'value_text': forms.Textarea(attrs={'rows': 3, 'class': BASE_TEXTAREA, 'placeholder': 'Text value...'}),
            'value_number': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.0001'}),
            'value_boolean': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'value_date': forms.DateInput(attrs={'type': 'date', 'class': BASE_INPUT}),
            'value_option': forms.Select(attrs={'class': BASE_SELECT}),
            'value_json': forms.Textarea(attrs={'rows': 4, 'class': BASE_TEXTAREA + ' font-mono text-sm', 'placeholder': '{"key": "value"}'}),
            'display_order': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
        }


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = '__all__'
        exclude = ['created_at', 'updated_at',
                   'available_quantity', 'sales_count']
        widgets = {
            'product': forms.Select(attrs={'class': BASE_SELECT}),
            'sku': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Variant SKU'}),
            'barcode': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Barcode'}),
            'mpn': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Manufacturer Part Number'}),
            'gtin': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Global Trade Item Number'}),
            'variant_name': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Variant display name'}),
            'option_values': forms.SelectMultiple(attrs={'class': BASE_SELECT, 'size': '4'}),
            'price': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'compare_at_price': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'cost_price': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'stock_quantity': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
            'reserved_quantity': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
            'weight': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.001', 'min': '0'}),
            'length': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'width': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'height': forms.NumberInput(attrs={'class': BASE_INPUT, 'step': '0.01', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'is_default': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
        }


class VariantImageForm(forms.ModelForm):
    class Meta:
        model = VariantImage
        fields = '__all__'
        exclude = ['created_at']
        widgets = {
            'variant': forms.Select(attrs={'class': BASE_SELECT}),
            'image': forms.ClearableFileInput(attrs={'class': BASE_FILE}),
            'alt_text': forms.TextInput(attrs={'class': BASE_INPUT, 'placeholder': 'Alt text for accessibility'}),
            'is_primary': forms.CheckboxInput(attrs={'class': BASE_CHECKBOX}),
            'display_order': forms.NumberInput(attrs={'class': BASE_INPUT, 'min': '0'}),
        }


# Formsets for inline editing
ProductImageFormSet = inlineformset_factory(
    Product, ProductImage, form=ProductImageForm, extra=1, can_delete=True)
ProductVideoFormSet = inlineformset_factory(
    Product, ProductVideo, form=ProductVideoForm, extra=1, can_delete=True)
# ProductDocumentFormSet = inlineformset_factory(
    # Product, ProductDocument, form=ProductDocumentForm, extra=1, can_delete=True)
ProductAttributeValueFormSet = inlineformset_factory(
    Product, ProductAttributeValue, form=ProductAttributeValueForm, extra=1, can_delete=True)
ProductVariantFormSet = inlineformset_factory(
    Product, ProductVariant, form=ProductVariantForm, extra=1, can_delete=True)
VariantImageFormSet = inlineformset_factory(
    ProductVariant, VariantImage, form=VariantImageForm, extra=1, can_delete=True)
AttributeValueFormSet = inlineformset_factory(
    Attribute, AttributeValue, form=AttributeValueForm, extra=1, can_delete=True)
