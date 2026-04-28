
"""
ENTERPRISE E-COMMERCE - PRODUCT CREATION FORMS
Comprehensive Django forms matching the HTML product creation interface
Based on complete_ecommerce_models.py
"""


from django import forms
from django.forms import formsets, inlineformset_factory, BaseModelFormSet
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils.text import slugify
from decimal import Decimal
from public.product.models import (
    Product, ProductImage, ProductVideo,
    # ProductDocument,
    ProductAttributeValue, Attribute, AttributeValue,
    ProductVariant, Category, Tag, Brand,
    # PriceRule, Specification, Feature
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
# PRODUCT BASIC INFORMATION FORM
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

    sku = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'e.g., PROD-001',
            'required': 'required'
        }),
        label='SKU *',
        validators=[RegexValidator(
            r'^[A-Z0-9\-]+$', 'SKU must contain only uppercase letters, numbers, and hyphens')]
    )

    product_type = forms.ChoiceField(
        choices=PRODUCT_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'block w-full max-w-md rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'id': 'productType',

        }),
        label='Product Type *',
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

    is_pos_available = forms.BooleanField(
        required=False,
        widget=ToggleSwitchWidget(attrs={
            'id': 'isPosAvailable',
        }),
        label='Available in POS',
        initial=False,
    )

    class Meta:
        model = Product
        fields = [
            'name', 'slug', 'sku', 'product_type', 'brand',
            'categories', 'tags', 'short_description', 'description',
            'is_pos_available',
        ]

    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        name = self.cleaned_data.get('name')

        # Always generate slug from name if name exists
        if name:
            base_slug = slugify(name)
            if not base_slug:
                import uuid
                base_slug = f'product-{str(uuid.uuid4())[:8]}'

            # Check for uniqueness
            counter = 1
            unique_slug = base_slug
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
            import uuid
            slug = f'product-{str(uuid.uuid4())[:8]}'

        return slug

    def clean_sku(self):
        sku = self.cleaned_data.get('sku')
        if sku:
            # Check uniqueness excluding current instance if editing
            queryset = Product.objects.filter(sku=sku)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise forms.ValidationError('This SKU is already in use.')
        return sku


# ============================================================================
# PRICING FORM
# ============================================================================

class ProductPricingForm(forms.ModelForm):
    """Product pricing information"""

    price = forms.DecimalField(
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
        label='Price *'
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
        initial='taxable'
    )

    class Meta:
        model = Product
        fields = ['price', 'compare_at_price',
                  'cost_price', 'tax_class', 'tax_status']

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get('price')
        compare_at_price = cleaned_data.get('compare_at_price')

        if price and compare_at_price:
            if compare_at_price <= price:
                raise forms.ValidationError(
                    'Compare at price must be greater than the sale price.'
                )

        return cleaned_data


# ============================================================================
# INVENTORY FORM
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
        initial='in_stock'
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
# SHIPPING FORM
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
# DIGITAL PRODUCT FORM
# ============================================================================

class ProductDigitalForm(forms.ModelForm):
    """Digital product settings"""

    is_downloadable = forms.BooleanField(
        required=False,
        widget=ToggleSwitchWidget(attrs={
            'id': 'isDownloadable',
            'onchange': 'toggleDigitalFields()'
        }),
        label='Downloadable Product',
        initial=False
    )

    download_limit = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'Leave empty for unlimited',
            'id': 'downloadLimit'
        }),
        label='Download Limit',
        help_text='Max downloads per purchase'
    )

    download_expiry = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'Leave empty for never',
            'id': 'downloadExpiry'
        }),
        label='Download Expiry (Days)',
        help_text='Days until download expires'
    )

    class Meta:
        model = Product
        fields = ['is_downloadable', 'download_limit', 'download_expiry']


# ============================================================================
# SUBSCRIPTION FORM
# ============================================================================

class ProductSubscriptionForm(forms.ModelForm):
    """Subscription product settings"""

    subscription_period = forms.ChoiceField(
        choices=[
            ('', 'Select Period'),
            ('day', 'Daily'),
            ('week', 'Weekly'),
            ('month', 'Monthly'),
            ('year', 'Yearly'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'id': 'subscriptionPeriod'
        }),
        label='Billing Period'
    )

    subscription_length = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'Leave empty for indefinite',
            'id': 'subscriptionLength'
        }),
        label='Billing Cycles',
        help_text='Number of periods'
    )

    trial_period = forms.ChoiceField(
        choices=[
            ('', 'No Trial'),
            ('day', 'Daily'),
            ('week', 'Weekly'),
            ('month', 'Monthly'),
            ('year', 'Yearly'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3'
        }),
        label='Trial Period'
    )

    trial_length = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3',
            'placeholder': 'Number of periods'
        }),
        label='Trial Length'
    )

    class Meta:
        model = Product
        fields = ['subscription_period', 'subscription_length',
                  'trial_period', 'trial_length']


# ============================================================================
# SEO FORM
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
# VISIBILITY & STATUS FORM
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
        initial='draft'
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

    # catalog_visibility = forms.ChoiceField(
    #     choices=[
    #         ('visible', 'Shop and Search'),
    #         ('catalog', 'Shop Only'),
    #         ('search', 'Search Only'),
    #         ('hidden', 'Hidden'),
    #     ],
    #     widget=forms.Select(attrs={
    #         'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-3'
    #     }),
    #     label='Catalog Visibility',
    #     initial='visible'
    # )

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
            'is_new', 'is_on_sale',  # 'catalog_visibility',
            'available_from', 'available_until'
        ]


# ============================================================================
# PURCHASE SETTINGS FORM
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
# PRODUCT IMAGE FORMSET
# ============================================================================

class ProductImageForm(forms.ModelForm):
    """Product image form"""

    image = forms.ImageField(
        widget=ImageUploadWidget(attrs={
            'class': 'image-upload-input',
            'accept': 'image/*'
        }),
        label='Image'
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

    title = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'placeholder': 'Image title'
        }),
        label='Title'
    )

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
        fields = ['image', 'alt_text', 'title',
                  'caption', 'is_primary', 'display_order']


# ============================================================================
# PRODUCT VIDEO FORMSET
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
# PRODUCT ATTRIBUTE VALUE FORMSET
# ============================================================================

class ProductAttributeValueForm(forms.ModelForm):
    """Product attribute value assignment form"""

    attribute = forms.ModelChoiceField(
        # queryset=Attribute.objects.filter(is_active=True),
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
# PRODUCT VARIANT FORMSET
# ============================================================================

class ProductVariantForm(forms.ModelForm):
    """Product variant form"""

    sku = forms.CharField(
        max_length=100,
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
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'w-20 px-2 py-1 border border-gray-300 rounded text-sm focus:border-primary-500 focus:ring-primary-500',
            'min': '0'
        }),
        label='Stock'
    )

    low_stock_threshold = forms.IntegerField(
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
        queryset=AttributeValue.objects.filter(is_active=True),
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


# ============================================================================
# MAIN PRODUCT CREATION FORM (Combines all forms)
# ============================================================================

class ProductCreationForm:
    """
    Main product creation form that combines all sub-forms.
    This is a form manager class, not a ModelForm.
    """

    def __init__(self, data=None, files=None, instance=None):
        self.data = data
        self.files = files
        self.instance = instance
        # self.prefix = prefix

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

        # self.digital_form = ProductDigitalForm(
        #     data=data, files=files, instance=instance
        # )

        # self.subscription_form = ProductSubscriptionForm(
        #     data=data, files=files, instance=instance
        # )

        self.seo_form = ProductSEOForm(
            data=data, files=files, instance=instance
        )

        self.visibility_form = ProductVisibilityForm(
            data=data, files=files, instance=instance
        )

        self.purchase_form = ProductPurchaseSettingsForm(
            data=data, files=files, instance=instance
        )

        # Initialize formsets with conditional requirements
        # self.image_formset = inlineformset_factory(
        #     Product, ProductImage, form=ProductImageForm,
        #     extra=1, can_delete=True, can_order=True, min_num=0, validate_min=False
        # )(data=data, files=files, instance=instance)

        # self.video_formset = inlineformset_factory(
        #     Product, ProductVideo, form=ProductVideoForm,
        #     extra=1, can_delete=True, can_order=True, min_num=0, validate_min=False
        # )(data=data, files=files, instance=instance)

        # self.attribute_formset = inlineformset_factory(
        #     Product, ProductAttributeValue, form=ProductAttributeValueForm,
        #     extra=1, can_delete=True, can_order=True, min_num=0, validate_min=False
        # )(data=data, files=files, instance=instance)

        self.variant_formset = inlineformset_factory(
            Product, ProductVariant, form=ProductVariantForm,
            extra=0, can_delete=True, can_order=True, min_num=0, validate_min=False
        )(data=data, files=files, instance=instance)

        # self.price_rule_formset = inlineformset_factory(
        #     Product, PriceRule, form=PriceRuleForm,
        #     extra=0, can_delete=True, can_order=True
        # )(data=data, files=files, instance=instance)

    def is_valid(self):
        """Validate all forms and formsets with conditional logic"""
        forms_valid = all([
            self.basic_form.is_valid(),
            self.pricing_form.is_valid(),
            self.inventory_form.is_valid(),
            self.shipping_form.is_valid(),
            # self.digital_form.is_valid(),
            # self.subscription_form.is_valid(),
            self.seo_form.is_valid(),
            self.visibility_form.is_valid(),
            self.purchase_form.is_valid(),
        ])

        # Validate variant formset
        variants_valid = self.variant_formset.is_valid()

        return forms_valid and variants_valid

    def _validate_conditional_requirements(self):
        """Validate conditional requirements based on product settings"""
        errors = []

        # Get form data
        status = self.visibility_form.cleaned_data.get(
            'status') if self.visibility_form.is_valid() else None
        product_type = self.basic_form.cleaned_data.get(
            'product_type') if self.basic_form.is_valid() else None

        # Check if images are required for published products
        if status == 'published':
            has_images = any(
                form.cleaned_data and not form.cleaned_data.get(
                    'DELETE', False)
                for form in self.image_formset.forms
                if form.cleaned_data.get('image')
            )

            if not has_images and not (self.instance and self.instance.images.exists()):
                errors.append(
                    "At least one image is required for published products.")

        # Check if attributes/variants are required for variable products
        if product_type == 'variable':
            has_attributes = any(
                form.cleaned_data and not form.cleaned_data.get(
                    'DELETE', False)
                for form in self.attribute_formset.forms
                if form.cleaned_data.get('attribute')
            )

            if not has_attributes and not (self.instance and self.instance.attribute_values.exists()):
                errors.append(
                    "Variable products must have at least one attribute defined.")

        # Store custom errors
        if errors:
            self._custom_errors = errors
            return False

        return True

    def save(self, commit=True):
        """Save all forms and formsets"""
        # Save main product instance
        product = self.basic_form.save(commit=commit)

        # Save all other forms
        self.pricing_form.save(commit=commit)
        self.inventory_form.save(commit=commit)
        self.shipping_form.save(commit=commit)
        # self.digital_form.save(commit=commit)
        # self.subscription_form.save(commit=commit)
        self.seo_form.save(commit=commit)
        self.visibility_form.save(commit=commit)
        self.purchase_form.save(commit=commit)

        # Save all formsets
        # self.image_formset.save(commit=commit)
        # self.video_formset.save(commit=commit)
        # # self.document_formset.save(commit=commit)
        # self.attribute_formset.save(commit=commit)
        self.variant_formset.save(commit=commit)
        # self.price_rule_formset.save(commit=commit)

        return product

    @property
    def errors(self):
        """Collect all errors from forms and formsets"""
        errors = {}

        # Collect form errors
        for name, form in [
            ('basic', self.basic_form),
            ('pricing', self.pricing_form),
            ('inventory', self.inventory_form),
            ('shipping', self.shipping_form),
            # ('digital', self.digital_form),
            # ('subscription', self.subscription_form),
            ('seo', self.seo_form),
            ('visibility', self.visibility_form),
            ('purchase', self.purchase_form),
        ]:
            if form.errors:
                errors[name] = form.errors

        # Collect formset errors
        # for name, formset in [
        #     ('images', self.image_formset),
        #     ('videos', self.video_formset),
        #     ('attributes', self.attribute_formset),
        #     ('variants', self.variant_formset),
        # ]:
        #     if formset.errors:
        #         errors[name] = formset.errors

        # Add custom conditional errors
        if hasattr(self, '_custom_errors') and self._custom_errors:
            errors['conditional'] = self._custom_errors

        return errors

    def get_context(self):
        """Get context for template rendering"""
        return {
            'basic_form': self.basic_form,
            'pricing_form': self.pricing_form,
            'inventory_form': self.inventory_form,
            'shipping_form': self.shipping_form,
            'digital_form': self.digital_form,
            'subscription_form': self.subscription_form,
            'seo_form': self.seo_form,
            'visibility_form': self.visibility_form,
            'purchase_form': self.purchase_form,
            'image_formset': self.image_formset,
            'video_formset': self.video_formset,
            'document_formset': self.document_formset,
            'attribute_formset': self.attribute_formset,
            'variant_formset': self.variant_formset,
            'price_rule_formset': self.price_rule_formset,
        }


# ============================================================================
# BULK PRODUCT IMPORT FORM
# ============================================================================

class BulkProductImportForm(forms.Form):
    """Form for bulk product import via CSV/Excel"""

    import_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100',
            'accept': '.csv,.xlsx,.xls'
        }),
        label='Import File',
        help_text='Upload CSV or Excel file with product data'
    )

    update_existing = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Update Existing Products',
        help_text='Check to update products with matching SKU',
        initial=False
    )

    skip_errors = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Skip Errors',
        help_text='Continue import even if some rows have errors',
        initial=False
    )

    notify_on_complete = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'checked': 'checked'
        }),
        label='Notify on Complete',
        help_text='Send email notification when import is complete',
        initial=True
    )


# ============================================================================
# PRODUCT EXPORT FORM
# ============================================================================

class ProductExportForm(forms.Form):
    """Form for exporting products"""

    export_format = forms.ChoiceField(
        choices=[
            ('csv', 'CSV'),
            ('xlsx', 'Excel'),
            ('json', 'JSON'),
            ('xml', 'XML'),
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Export Format',
        initial='csv'
    )

    include_images = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'checked': 'checked'
        }),
        label='Include Images',
        initial=True
    )

    include_variants = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'checked': 'checked'
        }),
        label='Include Variants',
        initial=True
    )

    include_attributes = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'checked': 'checked'
        }),
        label='Include Attributes',
        initial=True
    )

    status_filter = forms.MultipleChoiceField(
        choices=[
            ('draft', 'Draft'),
            ('pending', 'Pending'),
            ('private', 'Private'),
            ('published', 'Published'),
            ('archived', 'Archived'),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Filter by Status',
        initial=['published']
    )

    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'type': 'date'
        }),
        label='Created From'
    )

    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm border p-2',
            'type': 'date'
        }),
        label='Created To'
    )


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
