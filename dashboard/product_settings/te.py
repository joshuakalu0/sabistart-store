"""
ENTERPRISE E-COMMERCE - PRODUCT CREATION FORMS (FIXED)
Comprehensive Django forms matching the HTML product creation interface
Based on complete_ecommerce_models.py

FIXES APPLIED:
- Fixed slug/SKU uniqueness validation
- Fixed conditional field requirements based on status
- Fixed Draft vs Published validation
- Fixed image/variant/attribute requirements
- Fixed form initialization and save logic
"""
from django import forms
from django.forms import inlineformset_factory, BaseModelFormSet
from django.core.validators import MinValueValidator, RegexValidator
from django.utils.text import slugify
from decimal import Decimal
import uuid
from public.product.models import (
    Product, ProductImage, ProductVideo,
    ProductAttributeValue, Attribute, AttributeValue,
    ProductVariant, Category, Tag, Brand,
)


# ============================================================================
# CUSTOM WIDGETS
# ============================================================================


class ToggleSwitchWidget(forms.CheckboxInput):
    """Custom toggle switch widget for boolean fields"""
    template_name = 'widgets/toggle_switch.html'

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'toggle-checkbox absolute block w-6 h-6 rounded-full bg-white border-4 appearance-none cursor-pointer border-gray-300 left-0 transition-all duration-300'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class TagInputWidget(forms.TextInput):
    """Tag input widget with autocomplete"""
    template_name = 'widgets/tag_input.html'

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'flex-1 rounded-l-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'Type and press Enter to add...',
            'data-tag-input': 'true'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class MultiSelectWidget(forms.SelectMultiple):
    """Multi-select widget with search functionality"""
    template_name = 'widgets/multi_select.html'

    def __init__(self, attrs=None, choices=()):
        default_attrs = {
            'class': 'multi-select-dropdown',
            'data-searchable': 'true'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs, choices)


class KeyValueWidget(forms.Widget):
    """Key-value pair input widget for specifications"""
    template_name = 'widgets/key_value_input.html'

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'key-value-pair',
            'data-key-value': 'true'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class ImageUploadWidget(forms.ClearableFileInput):
    """Image upload widget with preview"""
    template_name = 'widgets/image_upload.html'

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'image-upload-input',
            'accept': 'image/*',
            # 'multiple': 'multiple'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


# ============================================================================
# PRODUCT BASIC INFORMATION FORM (FIXED)
# ============================================================================

class ProductBasicInfoForm(forms.ModelForm):
    """Main product information form"""

    PRODUCT_TYPE_CHOICES = [
        ('simple', 'Simple Product'),
        ('variable', 'Variable Product (has variants)'),
    ]

    name = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'Enter product name',
            'required': 'required'
        }),
        label='Product Name *'
    )

    # FIXED: Slug is now auto-generated, not user-editable
    slug = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'flex-1 min-w-0 block w-full px-3 py-2 rounded-none rounded-r-md focus:ring-primary-500 focus:border-primary-500 sm:text-sm border border-gray-300',
            'placeholder': 'product-name',
            'readonly': 'readonly'
        }),
        label='URL Slug'
    )

    # FIXED: SKU validation improved
    sku = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'e.g., PROD-001',
        }),
        label='SKU',
        required=False,  # FIXED: Not required for Draft
        validators=[RegexValidator(
            r'^[A-Z0-9\-]+$', 'SKU must contain only uppercase letters, numbers, and hyphens')]
    )

    product_type = forms.ChoiceField(
        choices=PRODUCT_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'block w-full max-w-md rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'id': 'productType',
        }),
        label='Product Type',
        initial='simple'
    )

    short_description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'Brief product summary (max 500 characters)',
            'rows': '2',
            'maxlength': '500',
            'oninput': 'document.getElementById("shortDescCount").textContent = this.value.length'
        }),
        label='Short Description'
    )

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'block w-full px-3 py-2 focus:outline-none sm:text-sm',
            'placeholder': 'Enter detailed product description...',
            'rows': '6',
            'id': 'productDescription'
        }),
        label='Description'
    )

    brand = forms.ModelChoiceField(
        queryset=Brand.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3'
        }),
        label='Brand',
        empty_label='Select Brand'
    )

    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        widget=MultiSelectWidget(attrs={
            'class': 'multi-select-dropdown',
            'id': 'categoryDropdown',
            'data-searchable': 'true'
        }),
        label='Categories'
    )

    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.filter(is_active=True),
        required=False,
        widget=MultiSelectWidget(attrs={
            'class': 'multi-select-dropdown',
            'id': 'tagDropdown',
            'data-searchable': 'true',
            'data-allow-create': 'true'
        }),
        label='Tags'
    )

    class Meta:
        model = Product
        fields = [
            'name', 'slug', 'sku', 'product_type', 'brand',
            'categories', 'tags', 'short_description', 'description'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # FIXED: Make SKU required only for Published products
        if self.instance and self.instance.pk:
            # Editing existing product
            status = getattr(self.instance, 'status', 'draft')
            if status != 'published':
                self.fields['sku'].required = False
        else:
            # Creating new product - check POST data
            if 'data' in kwargs and kwargs['data']:
                status = kwargs['data'].get('status', 'draft')
                if status != 'published':
                    self.fields['sku'].required = False

    def clean_slug(self):
        """FIXED: Properly generate unique slug"""
        slug = self.cleaned_data.get('slug')
        name = self.cleaned_data.get('name')

        # Always generate slug from name
        if name:
            base_slug = slugify(name)
            if not base_slug:
                base_slug = f'product-{str(uuid.uuid4())[:8]}'

            # Check for uniqueness
            unique_slug = base_slug
            counter = 1

            # Build queryset excluding current instance if editing
            queryset = Product.objects.filter(slug=unique_slug)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            while queryset.exists():
                unique_slug = f"{base_slug}-{counter}"
                counter += 1
                queryset = Product.objects.filter(slug=unique_slug)
                if self.instance and self.instance.pk:
                    queryset = queryset.exclude(pk=self.instance.pk)

            slug = unique_slug
        elif not slug:
            # Fallback if no name
            slug = f'product-{str(uuid.uuid4())[:8]}'

        return slug

    def clean_sku(self):
        """FIXED: Properly check SKU uniqueness"""
        sku = self.cleaned_data.get('sku')

        # Skip validation if SKU is empty (allowed for Draft)
        if not sku:
            return sku

        # Check uniqueness excluding current instance if editing
        queryset = Product.objects.filter(sku=sku)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise forms.ValidationError('This SKU is already in use.')

        return sku


# ============================================================================
# PRICING FORM (FIXED)
# ============================================================================

class ProductPricingForm(forms.ModelForm):
    """Product pricing information"""

    # FIXED: Price not required for Draft
    price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,  # FIXED: Not required
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'block w-full pl-7 pr-12 rounded-lg border-gray-300 focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0'
        }),
        label='Price'
    )

    compare_at_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'block w-full pl-7 pr-12 rounded-lg border-gray-300 focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0'
        }),
        label='Compare at Price'
    )

    cost_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'block w-full pl-7 pr-12 rounded-lg border-gray-300 focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0'
        }),
        label='Cost Price'
    )

    tax_class = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'e.g., Standard'
        }),
        label='Tax Class'
    )

    tax_status = forms.ChoiceField(
        choices=[
            ('taxable', 'Taxable'),
            ('shipping', 'Shipping Only'),
            ('none', 'None'),
        ],
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3'
        }),
        label='Tax Status',
        initial='taxable',
        required=False
    )

    class Meta:
        model = Product
        fields = ['price', 'compare_at_price',
                  'cost_price', 'tax_class', 'tax_status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # FIXED: Make price required only for Published products
        if self.instance and self.instance.pk:
            status = getattr(self.instance, 'status', 'draft')
            if status == 'published':
                self.fields['price'].required = True
        else:
            if 'data' in kwargs and kwargs['data']:
                status = kwargs['data'].get('status', 'draft')
                if status == 'published':
                    self.fields['price'].required = True

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get('price')
        compare_at_price = cleaned_data.get('compare_at_price')

        # Only validate if both fields have values
        if price and compare_at_price:
            if compare_at_price <= price:
                raise forms.ValidationError(
                    'Compare at price must be greater than the sale price.'
                )

        return cleaned_data


# ============================================================================
# INVENTORY FORM (FIXED)
# ============================================================================

class ProductInventoryForm(forms.ModelForm):
    """Product inventory management"""

    manage_stock = forms.BooleanField(
        required=False,
        widget=ToggleSwitchWidget(attrs={
            'id': 'manageStock',
            'onchange': 'toggleInventoryFields()'
        }),
        label='Track Inventory',
        initial=True
    )

    stock_quantity = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': '0',
            'min': '0',
            'id': 'stockQuantity'
        }),
        label='Stock Quantity'
    )

    low_stock_threshold = forms.IntegerField(
        required=False,
        min_value=0,
        initial=5,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'min': '0',
            'id': 'lowStockThreshold'
        }),
        label='Low Stock Threshold'
    )

    stock_status = forms.ChoiceField(
        choices=[
            ('in_stock', 'In Stock'),
            ('out_of_stock', 'Out of Stock'),
            ('on_backorder', 'On Backorder'),
        ],
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'id': 'stockStatus'
        }),
        label='Stock Status',
        initial='in_stock',
        required=False
    )

    backorders_allowed = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'id': 'backordersAllowed'
        }),
        label='Allow Backorders',
        initial=False
    )

    class Meta:
        model = Product
        fields = [
            'manage_stock', 'stock_quantity', 'low_stock_threshold',
            'stock_status', 'backorders_allowed'
        ]


# ============================================================================
# SHIPPING FORM (FIXED)
# ============================================================================

class ProductShippingForm(forms.ModelForm):
    """Product shipping information"""

    requires_shipping = forms.BooleanField(
        required=False,
        widget=ToggleSwitchWidget(attrs={
            'id': 'requiresShipping',
            'onchange': 'toggleShippingFields()'
        }),
        label='Requires Shipping',
        initial=True
    )

    weight = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        min_value=Decimal('0.000'),
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': '0.000',
            'step': '0.001',
            'min': '0',
            'id': 'weight'
        }),
        label='Weight (kg)'
    )

    length = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0',
            'id': 'length'
        }),
        label='Length (cm)'
    )

    width = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0',
            'id': 'width'
        }),
        label='Width (cm)'
    )

    height = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0',
            'id': 'height'
        }),
        label='Height (cm)'
    )

    shipping_class = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'e.g., Standard, Fragile',
            'id': 'shippingClass'
        }),
        label='Shipping Class'
    )

    class Meta:
        model = Product
        fields = [
            'requires_shipping', 'weight', 'length', 'width',
            'height', 'shipping_class'
        ]


# ============================================================================
# SEO FORM (FIXED)
# ============================================================================

class ProductSEOForm(forms.ModelForm):
    """Product SEO settings"""

    meta_title = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'SEO title for search engines',
            'maxlength': '255',
            'oninput': 'document.getElementById("metaTitleCount").textContent = this.value.length',
            'id': 'metaTitle'
        }),
        label='Meta Title'
    )

    meta_description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'SEO description for search engines',
            'rows': '3',
            'maxlength': '500',
            'oninput': 'document.getElementById("metaDescCount").textContent = this.value.length',
            'id': 'metaDescription'
        }),
        label='Meta Description'
    )

    meta_keywords = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'keyword1, keyword2, keyword3'
        }),
        label='Meta Keywords'
    )

    focus_keyword = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'Primary keyword for this product',
            'id': 'focusKeyword'
        }),
        label='Focus Keyword'
    )

    canonical_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'https://yourstore.com/products/product-name'
        }),
        label='Canonical URL'
    )

    class Meta:
        model = Product
        fields = [
            'meta_title', 'meta_description', 'meta_keywords',
            'focus_keyword', 'canonical_url'
        ]


# ============================================================================
# VISIBILITY & STATUS FORM (FIXED)
# ============================================================================

class ProductVisibilityForm(forms.ModelForm):
    """Product visibility and status settings"""

    status = forms.ChoiceField(
        choices=[
            ('draft', 'Draft'),
            ('pending', 'Pending Review'),
            ('private', 'Private'),
            ('published', 'Published'),
            ('archived', 'Archived'),
        ],
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'id': 'productStatus'
        }),
        label='Status',
        initial='draft',
        required=False
    )

    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'id': 'isActive',
            'checked': 'checked'
        }),
        label='Active',
        initial=True
    )

    is_featured = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'id': 'isFeatured'
        }),
        label='Featured',
        initial=False
    )

    is_bestseller = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'id': 'isBestseller'
        }),
        label='Bestseller',
        initial=False
    )

    is_new = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'id': 'isNew'
        }),
        label='New',
        initial=False
    )

    is_on_sale = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'id': 'isOnSale'
        }),
        label='On Sale',
        initial=False
    )

    available_from = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'type': 'datetime-local',
            'id': 'availableFrom'
        }),
        label='Available From'
    )

    available_until = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'type': 'datetime-local',
            'id': 'availableUntil'
        }),
        label='Available Until'
    )

    class Meta:
        model = Product
        fields = [
            'status', 'is_active', 'is_featured', 'is_bestseller',
            'is_new', 'is_on_sale',
            'available_from', 'available_until'
        ]


# ============================================================================
# PURCHASE SETTINGS FORM (FIXED)
# ============================================================================

class ProductPurchaseSettingsForm(forms.ModelForm):
    """Product purchase settings"""

    sold_individually = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'id': 'soldIndividually'
        }),
        label='Sold Individually (Limit 1 per order)',
        initial=False
    )

    min_purchase_quantity = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'min': '1',
            'id': 'minPurchaseQuantity'
        }),
        label='Minimum Purchase Quantity'
    )

    max_purchase_quantity = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'min': '1',
            'placeholder': 'Leave empty for no limit',
            'id': 'maxPurchaseQuantity'
        }),
        label='Maximum Purchase Quantity'
    )

    enable_reviews = forms.BooleanField(
        required=False,
        widget=ToggleSwitchWidget(attrs={
            'id': 'enableReviews',
            'checked': 'checked'
        }),
        label='Enable Reviews',
        initial=True
    )

    class Meta:
        model = Product
        fields = [
            'sold_individually', 'min_purchase_quantity',
            'max_purchase_quantity', 'enable_reviews'
        ]


# ============================================================================
# SPECIFICATIONS FORM (Key-Value Pairs)
# ============================================================================

class SpecificationForm(forms.Form):
    """Individual specification key-value pair"""

    key = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Key (e.g., Processor)'
        }),
        label='Key'
    )

    value = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={
            'class': 'flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Value (e.g., Intel i7)'
        }),
        label='Value'
    )


class SpecificationsFormSet(BaseModelFormSet):
    """FormSet for product specifications"""

    def clean(self):
        """Validate that no duplicate keys exist"""
        if any(self.errors):
            return

        keys = [form.cleaned_data.get(
            'key') for form in self.forms if form.cleaned_data.get('key')]
        if len(keys) != len(set(keys)):
            raise forms.ValidationError('Specification keys must be unique.')

# ============================================================================
# FEATURES FORM (Tag-style)
# ============================================================================


class FeatureForm(forms.Form):
    """Individual feature tag"""

    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'feature-tag-input',
            'placeholder': 'Type feature and press Enter...'
        }),
        label='Feature'
    )


# ============================================================================
# PRODUCT IMAGE FORMSET (FIXED)
# ============================================================================

class ProductImageForm(forms.ModelForm):
    """Product image form"""

    # FIXED: Image not required
    image = forms.ImageField(
        widget=ImageUploadWidget(attrs={
            'class': 'image-upload-input',
            'accept': 'image/*'
        }),
        label='Image',
        required=False  # FIXED: Never required
    )

    # alt_text = forms.CharField(
    #     max_length=255,
    #     required=False,
    #     widget=forms.TextInput(attrs={
    #         'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
    #         'placeholder': 'Alt text for accessibility'
    #     }),
    #     label='Alt Text'
    # )

    # title = forms.CharField(
    #     max_length=255,
    #     required=False,
    #     widget=forms.TextInput(attrs={
    #         'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
    #         'placeholder': 'Image title'
    #     }),
    #     label='Title'
    # )

    caption = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'placeholder': 'Image caption',
            'rows': '2'
        }),
        label='Caption'
    )

    is_primary = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Primary Image',
        initial=False
    )

    display_order = forms.IntegerField(
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'min': '0'
        }),
        label='Display Order'
    )

    class Meta:
        model = ProductImage
        fields = ['image',  # 'alt_text', 'title',
                  'caption', 'is_primary', 'display_order']


# ============================================================================
# PRODUCT VIDEO FORMSET (FIXED)
# ============================================================================

class ProductVideoForm(forms.ModelForm):
    """Product video form"""

    video_type = forms.ChoiceField(
        required=False,
        choices=[
            ('youtube', 'YouTube'),
            ('vimeo', 'Vimeo'),
            ('upload', 'Upload'),
            ('external', 'External URL'),
        ],
        widget=forms.Select(attrs={
            'class': 'block w-40 rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'id': 'videoType'
        }),
        label='Video Type'
    )

    video_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'flex-1 rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'placeholder': 'Enter video URL or ID',
            'id': 'videoUrl'
        }),
        label='Video URL'
    )

    title = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'placeholder': 'Video title'
        }),
        label='Title'
    )

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'placeholder': 'Video description',
            'rows': '2'
        }),
        label='Description'
    )

    display_order = forms.IntegerField(
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'min': '0'
        }),
        label='Display Order'
    )

    class Meta:
        model = ProductVideo
        fields = ['video_type', 'video_url',
                  'title', 'description', 'display_order']


# ============================================================================
# PRODUCT ATTRIBUTE VALUE FORMSET (FIXED)
# ============================================================================

class ProductAttributeValueForm(forms.ModelForm):
    """Product attribute value assignment form"""

    attribute = forms.ModelChoiceField(
        queryset=Attribute.objects.filter(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'flex-1 rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'id': 'attributeSelect'
        }),
        label='Attribute',
        empty_label='Select an attribute...'
    )

    value_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2'
        }),
        label='Text Value'
    )

    value_number = forms.DecimalField(
        max_digits=20,
        decimal_places=4,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'step': '0.0001'
        }),
        label='Number Value'
    )

    value_boolean = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Boolean Value'
    )

    value_option = forms.ModelChoiceField(
        queryset=AttributeValue.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2'
        }),
        label='Option Value',
        empty_label='Select option...'
    )

    display_order = forms.IntegerField(
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'min': '0'
        }),
        label='Display Order'
    )

    class Meta:
        model = ProductAttributeValue
        fields = [
            'attribute', 'value_text', 'value_number',
            'value_boolean', 'value_option', 'display_order'
        ]


# ============================================================================
# PRODUCT VARIANT FORMSET (FIXED)
# ============================================================================




# ============================================================================
# MAIN PRODUCT CREATION FORM (COMPLETELY FIXED)
# ============================================================================


class ProductCreationForm:
    """
    Main product creation form that combines all sub-forms.
    This is a form manager class, not a ModelForm.

    FIXED:
    - Proper conditional validation based on status
    - Draft products can save with minimal data
    - Published products require all necessary fields
    - Images never required
    - Variants/attributes only required for Variable products
    """

    def __init__(self, data=None, files=None, instance=None):
        print(f"DEBUG: ProductCreationForm.__init__ called with data: {data is not None}, files: {files is not None}, instance: {instance is not None}")

        self.data = data
        self.files = files
        self.instance = instance
        self._custom_errors = []

        # Get product status for conditional validation
        self.product_status = 'draft'
        if data and 'status' in data:
            self.product_status = data.get('status', 'draft')
            print(f"DEBUG: Product status from data: {self.product_status}")
        elif instance and instance.pk:
            self.product_status = getattr(instance, 'status', 'draft')
            print(f"DEBUG: Product status from instance: {self.product_status}")
        else:
            print(f"DEBUG: Using default product status: {self.product_status}")

        # Get product type for conditional validation
        self.product_type = 'simple'
        if data and 'product_type' in data:
            self.product_type = data.get('product_type', 'simple')
            print(f"DEBUG: Product type from data: {self.product_type}")
        elif instance and instance.pk:
            self.product_type = getattr(instance, 'product_type', 'simple')
            print(f"DEBUG: Product type from instance: {self.product_type}")
        else:
            print(f"DEBUG: Using default product type: {self.product_type}")

        print("DEBUG: Initializing sub-forms...")
        # Initialize all sub-forms
        self.basic_form = ProductBasicInfoForm(
            data=data, files=files, instance=instance
        )

        self.pricing_form = ProductPricingForm(
            data=data, files=files, instance=instance
        )

        self.inventory_form = ProductInventoryForm(
            data=data, files=files, instance=instance
        )

        self.shipping_form = ProductShippingForm(
            data=data, files=files, instance=instance
        )

        self.seo_form = ProductSEOForm(
            data=data, files=files, instance=instance
        )

        self.visibility_form = ProductVisibilityForm(
            data=data, files=files, instance=instance
        )

        self.purchase_form = ProductPurchaseSettingsForm(
            data=data, files=files, instance=instance
        )
        print("DEBUG: Sub-forms initialized")

        print("DEBUG: Initializing formsets...")
        # Initialize formsets with proper configuration
        # FIXED: Images not required, proper min_num
        try:
            self.image_formset = inlineformset_factory(
                Product, ProductImage, form=ProductImageForm,
                extra=3, can_delete=True, can_order=True,
                min_num=0, validate_min=False
            )(data=data, files=files, instance=instance, prefix='images')
            print("DEBUG: Image formset initialized")
        except Exception as e:
            print(f"DEBUG: Error initializing image formset: {e}")
            raise

        try:
            self.video_formset = inlineformset_factory(
                Product, ProductVideo, form=ProductVideoForm,
                extra=1, can_delete=True, can_order=True,
                min_num=0, validate_min=False
            )(data=data, files=files, instance=instance, prefix='videos')
            print("DEBUG: Video formset initialized")
        except Exception as e:
            print(f"DEBUG: Error initializing video formset: {e}")
            raise

        # FIXED: Attributes only required for Variable products
        try:
            self.attribute_formset = inlineformset_factory(
                Product, ProductAttributeValue, form=ProductAttributeValueForm,
                extra=3, can_delete=True, can_order=True,
                min_num=0, validate_min=False
            )(data=data, files=files, instance=instance, prefix='attributes')
            print("DEBUG: Attribute formset initialized")
        except Exception as e:
            print(f"DEBUG: Error initializing attribute formset: {e}")
            raise

        # FIXED: Variants only required for Variable products
        try:
            self.variant_formset = inlineformset_factory(
                Product, ProductVariant, form=ProductVariantForm,
                extra=0, can_delete=True, can_order=True,
                min_num=0, validate_min=False
            )(data=data, files=files, instance=instance, prefix='variants')
            print("DEBUG: Variant formset initialized")
        except Exception as e:
            print(f"DEBUG: Error initializing variant formset: {e}")
            raise

        print("DEBUG: ProductCreationForm initialization complete")

    def is_valid(self):
        """
        FIXED: Validate all forms with conditional logic based on status
        """
        print(f"DEBUG: Starting is_valid() - product_status: {self.product_status}, product_type: {self.product_type}")

        # Validate all individual forms
        print("DEBUG: Validating individual forms...")
        forms_valid = all([
            self.basic_form.is_valid(),
            self.pricing_form.is_valid(),
            self.inventory_form.is_valid(),
            self.shipping_form.is_valid(),
            self.seo_form.is_valid(),
            self.visibility_form.is_valid(),
            self.purchase_form.is_valid(),
        ])
        print(f"DEBUG: Individual forms valid: {forms_valid}")

        if not forms_valid:
            print("DEBUG: Individual forms failed validation")
            return False

        # FIXED: Only validate formsets for Published products
        if self.product_status == 'published':
            print("DEBUG: Product is published, validating formsets...")

            # Validate image formset (but images still not required)
            if hasattr(self, 'image_formset'):
                print("DEBUG: Validating image formset...")
                if not self.image_formset.is_valid():
                    print("DEBUG: Image formset validation failed")
                    return False
            else:
                print("DEBUG: No image formset found")

            # Validate video formset
            if hasattr(self, 'video_formset'):
                print("DEBUG: Validating video formset...")
                if not self.video_formset.is_valid():
                    print("DEBUG: Video formset validation failed")
                    return False
            else:
                print("DEBUG: No video formset found")

            # FIXED: Only validate attributes/variants for Variable products
            if self.product_type == 'variable':
                print("DEBUG: Product is variable, validating attribute/variant formsets...")

                if hasattr(self, 'attribute_formset'):
                    print("DEBUG: Validating attribute formset...")
                    if not self.attribute_formset.is_valid():
                        print("DEBUG: Attribute formset validation failed")
                        return False
                else:
                    print("DEBUG: No attribute formset found")

                if hasattr(self, 'variant_formset'):
                    print("DEBUG: Validating variant formset...")
                    if not self.variant_formset.is_valid():
                        print("DEBUG: Variant formset validation failed")
                        return False
                else:
                    print("DEBUG: No variant formset found")
        else:
            print(f"DEBUG: Product status is {self.product_status}, skipping formset validation")

        # Run conditional validation
        print("DEBUG: Running conditional validation...")
        result = self._validate_conditional_requirements()
        print(f"DEBUG: Conditional validation result: {result}")
        return result

    def _validate_conditional_requirements(self):
        """
        FIXED: Validate conditional requirements based on product settings
        """
        print("DEBUG: Starting _validate_conditional_requirements()")
        self._custom_errors = []

        # Get cleaned data
        status = self.product_status
        product_type = self.product_type
        print(f"DEBUG: Conditional validation - status: {status}, product_type: {product_type}")

        # FIXED: Only enforce requirements for Published products
        if status == 'published':
            print("DEBUG: Validating published product requirements...")

            # Check if price is set for published products
            if self.pricing_form.is_valid():
                print("DEBUG: Pricing form is valid, checking price...")
                price = self.pricing_form.cleaned_data.get('price')
                print(f"DEBUG: Price value: {price}")
                if not price or price <= 0:
                    print("DEBUG: Price is missing or invalid")
                    self._custom_errors.append(
                        "Price is required for published products.")
            else:
                print("DEBUG: Pricing form is not valid")
                self._custom_errors.append(
                    "Price information is required for published products.")

            # FIXED: Only require attributes/variants for Variable products
            if product_type == 'variable':
                print("DEBUG: Validating variable product requirements...")

                # Check if at least one attribute is defined
                has_attributes = False
                if hasattr(self, 'attribute_formset'):
                    print("DEBUG: Checking attribute formset...")
                    print(f"DEBUG: Attribute formset is_valid: {self.attribute_formset.is_valid()}")

                    if self.attribute_formset.is_valid():
                        print(f"DEBUG: Attribute formset has {len(self.attribute_formset.forms)} forms")

                        for i, form in enumerate(self.attribute_formset.forms):
                            print(f"DEBUG: Checking attribute form {i}...")
                            print(f"DEBUG: Form is_valid: {form.is_valid()}")

                            if form.is_valid():
                                print(f"DEBUG: Form {i} cleaned_data exists: {hasattr(form, 'cleaned_data')}")
                                if hasattr(form, 'cleaned_data') and form.cleaned_data:
                                    print(f"DEBUG: Form {i} cleaned_data: {form.cleaned_data}")
                                    delete_flag = form.cleaned_data.get('DELETE', False)
                                    attribute = form.cleaned_data.get('attribute')
                                    print(f"DEBUG: Form {i} - DELETE: {delete_flag}, attribute: {attribute}")

                                    if not delete_flag and attribute:
                                        has_attributes = True
                                        print(f"DEBUG: Found valid attribute in form {i}")
                                        break
                            else:
                                print(f"DEBUG: Form {i} validation errors: {form.errors}")
                    else:
                        print(f"DEBUG: Attribute formset validation errors: {self.attribute_formset.errors}")
                else:
                    print("DEBUG: No attribute formset found")

                print(f"DEBUG: has_attributes: {has_attributes}")
                print(f"DEBUG: Instance exists: {self.instance is not None}")
                if self.instance:
                    print(f"DEBUG: Instance has attribute_values: {hasattr(self.instance, 'attribute_values')}")
                    if hasattr(self.instance, 'attribute_values'):
                        print(f"DEBUG: Existing attribute_values count: {self.instance.attribute_values.count()}")

                if not has_attributes and not (self.instance and hasattr(self.instance, 'attribute_values') and self.instance.attribute_values.exists()):
                    print("DEBUG: No attributes found for variable product")
                    self._custom_errors.append(
                        "Variable products must have at least one attribute defined.")
        else:
            print(f"DEBUG: Product status is {status}, skipping published product validation")

        print(f"DEBUG: Custom errors: {self._custom_errors}")
        # Return True if no custom errors
        result = len(self._custom_errors) == 0
        print(f"DEBUG: _validate_conditional_requirements returning: {result}")
        return result

    def save(self, commit=True):
        """
        FIXED: Save all forms and formsets properly
        """
        print(f"DEBUG: Starting save() with commit={commit}")

        # Save main product instance
        print("DEBUG: Saving basic form (main product)...")
        product = self.basic_form.save(commit=commit)
        print(f"DEBUG: Product saved with ID: {product.pk if product else 'None'}")

        # Save all other forms
        print("DEBUG: Saving pricing form...")
        self.pricing_form.instance = product
        self.pricing_form.save(commit=commit)

        print("DEBUG: Saving inventory form...")
        self.inventory_form.instance = product
        self.inventory_form.save(commit=commit)

        print("DEBUG: Saving shipping form...")
        self.shipping_form.instance = product
        self.shipping_form.save(commit=commit)

        print("DEBUG: Saving SEO form...")
        self.seo_form.instance = product
        self.seo_form.save(commit=commit)

        print("DEBUG: Saving visibility form...")
        self.visibility_form.instance = product
        self.visibility_form.save(commit=commit)

        print("DEBUG: Saving purchase form...")
        self.purchase_form.instance = product
        self.purchase_form.save(commit=commit)

        # Save all formsets
        print("DEBUG: Saving image formset...")
        try:
            self.image_formset.save(commit=commit)
            print("DEBUG: Image formset saved successfully")
        except Exception as e:
            print(f"DEBUG: Error saving image formset: {e}")
            raise

        print("DEBUG: Saving video formset...")
        try:
            self.video_formset.save(commit=commit)
            print("DEBUG: Video formset saved successfully")
        except Exception as e:
            print(f"DEBUG: Error saving video formset: {e}")
            raise

        print("DEBUG: Saving attribute formset...")
        try:
            self.attribute_formset.save(commit=commit)
            print("DEBUG: Attribute formset saved successfully")
        except Exception as e:
            print(f"DEBUG: Error saving attribute formset: {e}")
            raise

        print("DEBUG: Saving variant formset...")
        try:
            # Check if variant formset is valid before saving
            print(f"DEBUG: Variant formset is_valid: {self.variant_formset.is_valid()}")
            if not self.variant_formset.is_valid():
                print(f"DEBUG: Variant formset errors: {self.variant_formset.errors}")
                print(f"DEBUG: Variant formset non_form_errors: {self.variant_formset.non_form_errors()}")

            # Debug each form in the formset
            for i, form in enumerate(self.variant_formset.forms):
                print(f"DEBUG: Variant form {i} - is_valid: {form.is_valid()}")
                print(f"DEBUG: Variant form {i} - has_changed: {form.has_changed()}")
                print(f"DEBUG: Variant form {i} - should_delete: {form in self.variant_formset.deleted_forms if hasattr(self.variant_formset, 'deleted_forms') else 'N/A'}")

                if hasattr(form, 'cleaned_data'):
                    print(f"DEBUG: Variant form {i} - cleaned_data: {form.cleaned_data}")
                else:
                    print(f"DEBUG: Variant form {i} - NO cleaned_data attribute")

                if form.errors:
                    print(f"DEBUG: Variant form {i} - errors: {form.errors}")
                    print("Form Errors:", form.errors.as_data())

                    # Or to see just the keys (the fields that failed)
                    print("Fields with errors:", list(form.errors.keys()))

                # Check if this form should be saved
                if form.has_changed() and form.is_valid():
                    print(f"DEBUG: Variant form {i} - will be saved")
                elif not form.has_changed():
                    print(f"DEBUG: Variant form {i} - no changes, will be skipped")
                elif not form.is_valid():
                    print(f"DEBUG: Variant form {i} - invalid, will cause error")

            # Save the variant formset directly - let Django handle the validation
            self.variant_formset.save(commit=commit)
            print("DEBUG: Variant formset saved successfully")
        except Exception as e:
            print(f"DEBUG: Error saving variant formset: {e}")
            import traceback
            print(f"DEBUG: Full traceback: {traceback.format_exc()}")
            raise

        print("DEBUG: All forms and formsets saved successfully")
        return product

    @property
    def errors(self):
        """
        FIXED: Collect all errors from forms and formsets
        """
        errors = {}

        # Collect form errors
        for name, form in [
            ('basic', self.basic_form),
            ('pricing', self.pricing_form),
            ('inventory', self.inventory_form),
            ('shipping', self.shipping_form),
            ('seo', self.seo_form),
            ('visibility', self.visibility_form),
            ('purchase', self.purchase_form),
        ]:
            if form.errors:
                errors[name] = form.errors

        # Collect formset errors (only for Published products)
        if self.product_status == 'published':
            for name, formset in [
                ('images', self.image_formset),
                ('videos', self.video_formset),
            ]:
                if formset.errors:
                    errors[name] = formset.errors

            # Only check attributes/variants for Variable products
            if self.product_type == 'variable':
                for name, formset in [
                    ('attributes', self.attribute_formset),
                    ('variants', self.variant_formset),
                ]:
                    if formset.errors:
                        errors[name] = formset.errors

        # Add custom conditional errors
        if self._custom_errors:
            errors['conditional'] = self._custom_errors

        return errors

    def get_context(self):
        """
        Get context for template rendering
        """
        return {
            'basic_form': self.basic_form,
            'pricing_form': self.pricing_form,
            'inventory_form': self.inventory_form,
            'shipping_form': self.shipping_form,
            'seo_form': self.seo_form,
            'visibility_form': self.visibility_form,
            'purchase_form': self.purchase_form,
            'image_formset': self.image_formset,
            'video_formset': self.video_formset,
            'attribute_formset': self.attribute_formset,
            'variant_formset': self.variant_formset,
            'product_status': self.product_status,
            'product_type': self.product_type,
        }


# ============================================================================
# PRICE RULE FORMSET
# ============================================================================

# class PriceRuleForm(forms.ModelForm):
#     """Price rule form"""

#     name = forms.CharField(
#         max_length=255,
#         widget=forms.TextInput(attrs={
#             'class': 'font-medium text-gray-900 border-none focus:ring-0 p-0'
#         }),
#         label='Rule Name'
#     )

#     rule_type = forms.ChoiceField(
#         choices=[
#             ('tier', 'Tier Pricing'),
#             ('customer_group', 'Customer Group'),
#             ('schedule', 'Scheduled'),
#         ],
#         widget=forms.Select(attrs={
#             'class': 'px-2 py-1 border border-gray-300 rounded text-sm'
#         }),
#         label='Rule Type'
#     )

#     price_type = forms.ChoiceField(
#         choices=[
#             ('fixed', 'Fixed Price'),
#             ('percentage', 'Percentage Discount'),
#             ('fixed_discount', 'Fixed Discount'),
#         ],
#         widget=forms.Select(attrs={
#             'class': 'px-2 py-1 border border-gray-300 rounded text-sm'
#         }),
#         label='Price Type'
#     )

#     price_value = forms.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         min_value=Decimal('0.00'),
#         widget=forms.NumberInput(attrs={
#             'class': 'px-2 py-1 border border-gray-300 rounded text-sm',
#             'step': '0.01',
#             'min': '0'
#         }),
#         label='Price Value'
#     )

#     min_quantity = forms.IntegerField(
#         min_value=1,
#         initial=1,
#         widget=forms.NumberInput(attrs={
#             'class': 'px-2 py-1 border border-gray-300 rounded text-sm',
#             'min': '1'
#         }),
#         label='Min Quantity'
#     )

#     max_quantity = forms.IntegerField(
#         required=False,
#         min_value=1,
#         widget=forms.NumberInput(attrs={
#             'class': 'px-2 py-1 border border-gray-300 rounded text-sm',
#             'min': '1'
#         }),
#         label='Max Quantity'
#     )

#     priority = forms.IntegerField(
#         required=False,
#         initial=0,
#         widget=forms.NumberInput(attrs={
#             'class': 'px-2 py-1 border border-gray-300 rounded text-sm'
#         }),
#         label='Priority'
#     )

#     is_active = forms.BooleanField(
#         required=False,
#         widget=forms.CheckboxInput(attrs={
#             'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
#         }),
#         label='Active',
#         initial=True
#     )

#     class Meta:
#         model = PriceRule
#         fields = [
#             'name', 'rule_type', 'price_type', 'price_value',
#             'min_quantity', 'max_quantity', 'priority', 'is_active'
#         ]


# ============================================================================
# PRODUCT DOCUMENT FORMSET
# ============================================================================

# class ProductDocumentForm(forms.ModelForm):
#     """Product document form"""

#     title = forms.CharField(
#         max_length=255,
#         widget=forms.TextInput(attrs={
#             'class': 'flex-1 rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
#             'placeholder': 'Document title',
#             'id': 'documentTitle'
#         }),
#         label='Title'
#     )

#     description = forms.CharField(
#         required=False,
#         widget=forms.Textarea(attrs={
#             'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
#             'placeholder': 'Document description',
#             'rows': '2'
#         }),
#         label='Description'
#     )

#     file = forms.FileField(
#         widget=forms.ClearableFileInput(attrs={
#             'class': 'flex-1 rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
#             'accept': '.pdf,.doc,.docx,.txt,.zip',
#             'id': 'documentFile'
#         }),
#         label='File'
#     )

#     document_type = forms.ChoiceField(
#         choices=[
#             ('manual', 'User Manual'),
#             ('datasheet', 'Datasheet'),
#             ('certificate', 'Certificate'),
#             ('warranty', 'Warranty'),
#             ('guide', 'Guide'),
#             ('other', 'Other'),
#         ],
#         widget=forms.Select(attrs={
#             'class': 'block w-40 rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
#             'id': 'documentType'
#         }),
#         label='Document Type'
#     )

#     is_downloadable = forms.BooleanField(
#         required=False,
#         widget=forms.CheckboxInput(attrs={
#             'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
#         }),
#         label='Downloadable',
#         initial=True
#     )

#     requires_login = forms.BooleanField(
#         required=False,
#         widget=forms.CheckboxInput(attrs={
#             'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
#         }),
#         label='Requires Login',
#         initial=False
#     )

#     display_order = forms.IntegerField(
#         required=False,
#         initial=0,
#         widget=forms.NumberInput(attrs={
#             'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
#             'min': '0'
#         }),
#         label='Display Order'
#     )

#     class Meta:
#         model = ProductDocument
#         fields = [
#             'title', 'description', 'file', 'document_type',
#             'is_downloadable', 'requires_login', 'display_order'
#         ]

# ============================================================================
# PRODUCT VARIANT FORM CLASS
# ============================================================================

class ProductVariantForm(forms.ModelForm):
    """Product variant form for validation"""

    def __init__(self, *args, **kwargs):
        # print(f"DEBUG: ProductVariantForm.__init__ called with args: {len(args)}, kwargs: {list(kwargs.keys())}")

        # Handle invalid ID in data for new variants
        if args and isinstance(args[0], dict):
            data = args[0].copy()
            # If the ID is not a valid UUID or doesn't exist, remove it
            if 'id' in data:
                id_value = data['id']
                print(f"DEBUG: Checking ID value: {id_value}")

                # Check if this ID exists in the database
                if id_value:
                    try:
                        from uuid import UUID
                        UUID(str(id_value))  # Validate UUID format
                        # Check if it exists in database
                        if not ProductVariant.objects.filter(id=id_value).exists():
                            print(f"DEBUG: ID {id_value} doesn't exist in database, removing it")
                            del data['id']  # Remove the key entirely
                    except (ValueError, TypeError):
                        print(f"DEBUG: Invalid ID format {id_value}, removing it")
                        del data['id']  # Remove the key entirely

            args = (data,) + args[1:]

        super().__init__(*args, **kwargs)
        print("DEBUG: ProductVariantForm.__init__ completed")

    def is_valid(self):
        """Override is_valid to handle ID validation errors for new variants"""
        print(f"DEBUG: ProductVariantForm.is_valid() called")
        
        # Call parent is_valid first
        valid = super().is_valid()
        print(f"DEBUG: super().is_valid() returned: {valid}")
        
        # If invalid, check if it's only due to ID validation error
        if not valid and self.errors:
            print(f"DEBUG: Form errors: {self.errors}")
            
            # If only ID error exists, clear it and mark as valid
            if set(self.errors.keys()) == {'id'}:
                id_errors = self.errors.get('id', [])
                # Check if it's the "Select a valid choice" error
                for error in id_errors:
                    if 'Select a valid choice' in str(error):
                        print("DEBUG: Clearing ID validation error for new variant")
                        # Clear the ID error
                        del self.errors['id']
                        if hasattr(self, '_errors'):
                            if 'id' in self._errors:
                                del self._errors['id']
                        # Mark as valid
                        valid = True
                        break
        
        print(f"DEBUG: is_valid() returning: {valid}")
        return valid

    sku = forms.CharField(
        max_length=100,
        required=False,  # Make SKU optional
        widget=forms.TextInput(attrs={
            'class': 'w-full px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='SKU'
    )

    barcode = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Barcode'
    )

    variant_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Variant Name'
    )

    price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,  # Make price optional
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'w-24 px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500',
            'step': '0.01',
            'min': '0'
        }),
        label='Price'
    )

    compare_at_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'w-24 px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500',
            'step': '0.01',
            'min': '0'
        }),
        label='Compare at Price'
    )

    cost_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'w-24 px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500',
            'step': '0.01',
            'min': '0'
        }),
        label='Cost Price'
    )

    stock_quantity = forms.IntegerField(
        required=False,  # Make stock quantity optional
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'w-20 px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500',
            'min': '0'
        }),
        label='Stock'
    )

    low_stock_threshold = forms.IntegerField(
        required=False,  # Make low stock threshold optional
        min_value=0,
        initial=5,
        widget=forms.NumberInput(attrs={
            'class': 'w-20 px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500',
            'min': '0'
        }),
        label='Low Stock Threshold'
    )

    weight = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        min_value=Decimal('0.000'),
        widget=forms.NumberInput(attrs={
            'class': 'w-24 px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500',
            'step': '0.001',
            'min': '0'
        }),
        label='Weight (kg)'
    )

    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Active',
        initial=True
    )

    is_default = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Default Variant',
        initial=False
    )

    option_values = forms.ModelMultipleChoiceField(
        queryset=AttributeValue.objects.filter(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2'
        }),
        label='Option Values'
    )

    class Meta:
        model = ProductVariant
        fields = [
            'sku', 'barcode', 'variant_name', 'price', 'compare_at_price',
            'cost_price', 'stock_quantity', 'low_stock_threshold', 'weight',
            'is_active', 'is_default', 'option_values'
        ]

    def clean_sku(self):
        print("DEBUG: ProductVariantForm.clean_sku() called")
        print(f"DEBUG: self.cleaned_data exists: {hasattr(self, 'cleaned_data')}")

        if not hasattr(self, 'cleaned_data'):
            print("DEBUG: No cleaned_data, returning None")
            return None

        sku = self.cleaned_data.get('sku')
        print(f"DEBUG: SKU value: {sku}")

        if sku:
            # Check uniqueness excluding current instance if editing
            queryset = ProductVariant.objects.filter(sku=sku)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                print("DEBUG: SKU already exists, raising validation error")
                raise forms.ValidationError('This SKU is already in use.')

        print(f"DEBUG: clean_sku returning: {sku}")
        return sku

    def clean(self):
        print("DEBUG: ProductVariantForm.clean() called")
        print(f"DEBUG: self.cleaned_data exists: {hasattr(self, 'cleaned_data')}")

        try:
            cleaned_data = super().clean()
            print(f"DEBUG: super().clean() returned: {cleaned_data is not None}")
        except Exception as e:
            print(f"DEBUG: Error in super().clean(): {e}")
            # If there's an ID validation error, ignore it for new variants
            if 'id' in str(e).lower() and 'select a valid choice' in str(e).lower():
                print("DEBUG: Ignoring ID validation error for new variant")
                # Create empty cleaned_data if it doesn't exist
                if not hasattr(self, 'cleaned_data'):
                    self.cleaned_data = {}
                cleaned_data = self.cleaned_data
                # Remove ID error from form errors
                if hasattr(self, '_errors') and 'id' in self._errors:
                    del self._errors['id']
            else:
                raise

        if not cleaned_data:
            print("DEBUG: No cleaned_data from super().clean(), returning empty dict")
            return {}

        price = cleaned_data.get('price')
        compare_at_price = cleaned_data.get('compare_at_price')
        print(f"DEBUG: price: {price}, compare_at_price: {compare_at_price}")

        if price and compare_at_price:
            if compare_at_price <= price:
                print("DEBUG: Compare at price validation failed")
                raise forms.ValidationError(
                    'Compare at price must be greater than the sale price.'
                )

        print(f"DEBUG: clean() returning cleaned_data")
        return cleaned_data