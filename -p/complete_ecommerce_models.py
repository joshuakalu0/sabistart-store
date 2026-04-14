"""
ENTERPRISE E-COMMERCE MODELS - COMPREHENSIVE SYSTEM
====================================================
Handles EVERYTHING: Products, Variants, Pricing, Inventory, Discounts, 
Promotions, Bundles, Subscriptions, Gift Cards, Loyalty, Reviews, and more.

This is a COMPLETE system, not a toy.
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from decimal import Decimal
import uuid

User = get_user_model()


# ============================================================================
# CORE: CATEGORIES & TAXONOMIES
# ============================================================================

class Category(models.Model):
    """
    Hierarchical product categorization with unlimited depth.
    Supports multiple classification hierarchies.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    
    # Content
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/%Y/%m/', blank=True, null=True)
    icon = models.CharField(max_length=100, blank=True, help_text="CSS icon class or emoji")
    
    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(max_length=500, blank=True)
    meta_keywords = models.TextField(blank=True)
    canonical_url = models.URLField(blank=True)
    
    # Display
    display_order = models.IntegerField(default=0, db_index=True)
    featured = models.BooleanField(default=False, db_index=True)
    show_in_menu = models.BooleanField(default=True)
    menu_order = models.IntegerField(default=0)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    is_visible = models.BooleanField(default=True)
    
    # Analytics
    view_count = models.PositiveBigIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['parent', 'is_active', 'display_order']),
            models.Index(fields=['slug', 'is_active']),
            models.Index(fields=['featured', 'is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Tag(models.Model):
    """Product tags for flexible classification"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    color = models.CharField(max_length=7, default='#000000')
    icon = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    
    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(max_length=500, blank=True)
    
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ============================================================================
# CORE: BRANDS & MANUFACTURERS
# ============================================================================

class Brand(models.Model):
    """Brand/Manufacturer management"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    
    # Content
    description = models.TextField(blank=True)
    story = models.TextField(blank=True, help_text="Brand story/about")
    logo = models.ImageField(upload_to='brands/%Y/%m/', blank=True, null=True)
    banner = models.ImageField(upload_to='brands/banners/%Y/%m/', blank=True, null=True)
    
    # Contact
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    
    # Social
    facebook = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    
    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(max_length=500, blank=True)
    meta_keywords = models.TextField(blank=True)
    
    # Display
    featured = models.BooleanField(default=False, db_index=True)
    display_order = models.IntegerField(default=0)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ============================================================================
# CORE: ATTRIBUTES SYSTEM (Dynamic Product Properties)
# ============================================================================

class AttributeGroup(models.Model):
    """Group related attributes together"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return self.name


class Attribute(models.Model):
    """
    Product attribute definition (Color, Size, Material, etc.)
    Extremely flexible to handle any product property.
    """
    TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('decimal', 'Decimal'),
        ('boolean', 'Boolean'),
        ('color', 'Color'),
        ('date', 'Date'),
        ('url', 'URL'),
        ('email', 'Email'),
        ('file', 'File'),
        ('image', 'Image'),
        ('select', 'Select (Single)'),
        ('multiselect', 'Multi-Select'),
        ('range', 'Range'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    attribute_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='text')
    group = models.ForeignKey(AttributeGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='attributes')
    
    # Configuration
    description = models.TextField(blank=True)
    help_text = models.CharField(max_length=255, blank=True)
    unit = models.CharField(max_length=50, blank=True, help_text="e.g., cm, kg, etc.")
    
    # Validation
    is_required = models.BooleanField(default=False)
    is_unique = models.BooleanField(default=False)
    min_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    regex_pattern = models.CharField(max_length=500, blank=True)
    
    # Usage
    is_variant_option = models.BooleanField(default=False, help_text="Used to create variants")
    is_filterable = models.BooleanField(default=True, help_text="Show in filters")
    is_searchable = models.BooleanField(default=True, help_text="Include in search")
    is_comparable = models.BooleanField(default=True, help_text="Show in comparison")
    
    # Display
    display_order = models.IntegerField(default=0)
    is_visible_on_front = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class AttributeValue(models.Model):
    """Predefined values for select-type attributes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, db_index=True)
    
    # Visual representation
    color_hex = models.CharField(max_length=7, blank=True, help_text="For color attributes")
    image = models.ImageField(upload_to='attributes/%Y/%m/', blank=True, null=True)
    swatch = models.ImageField(upload_to='attributes/swatches/%Y/%m/', blank=True, null=True)
    
    # Additional data
    description = models.TextField(blank=True)
    extra_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Additional cost")
    
    # Display
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['attribute', 'display_order', 'value']
        unique_together = [['attribute', 'slug']]
    
    def __str__(self):
        return f"{self.attribute.name}: {self.value}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.value)
        super().save(*args, **kwargs)


# ============================================================================
# CORE: PRODUCTS
# ============================================================================

class Product(models.Model):
    """
    Main product entity. Can have multiple variants.
    Think of this as the "product family".
    """
    TYPE_CHOICES = [
        ('simple', 'Simple Product'),
        ('variable', 'Variable Product (has variants)'),
        ('grouped', 'Grouped Product'),
        ('bundle', 'Bundle'),
        ('subscription', 'Subscription'),
        ('digital', 'Digital/Downloadable'),
        ('service', 'Service'),
        ('rental', 'Rental'),
        ('gift_card', 'Gift Card'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Basic Info
    name = models.CharField(max_length=500, db_index=True)
    slug = models.SlugField(max_length=500, unique=True, db_index=True)
    sku = models.CharField(max_length=100, unique=True, db_index=True, help_text="Stock Keeping Unit")
    
    # Type & Classification
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='simple', db_index=True)
    categories = models.ManyToManyField(Category, related_name='products', blank=True)
    tags = models.ManyToManyField(Tag, related_name='products', blank=True)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    
    # Content
    short_description = models.TextField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    specifications = models.JSONField(default=dict, blank=True, help_text="Technical specs as JSON")
    features = models.JSONField(default=list, blank=True, help_text="Feature list as JSON array")
    
    # Pricing (for simple products, variants override these)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    
    # Tax
    tax_class = models.CharField(max_length=100, blank=True)
    tax_status = models.CharField(max_length=20, choices=[('taxable', 'Taxable'), ('shipping', 'Shipping Only'), ('none', 'None')], default='taxable')
    
    # Inventory (for simple products)
    manage_stock = models.BooleanField(default=True)
    stock_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    stock_status = models.CharField(max_length=20, choices=[('in_stock', 'In Stock'), ('out_of_stock', 'Out of Stock'), ('on_backorder', 'On Backorder')], default='in_stock', db_index=True)
    low_stock_threshold = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    backorders_allowed = models.BooleanField(default=False)
    
    # Shipping
    requires_shipping = models.BooleanField(default=True)
    weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, help_text="Weight in kg")
    length = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Length in cm")
    width = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Width in cm")
    height = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Height in cm")
    shipping_class = models.CharField(max_length=100, blank=True)
    
    # Digital Products
    is_downloadable = models.BooleanField(default=False)
    download_limit = models.IntegerField(null=True, blank=True, help_text="Max downloads per purchase")
    download_expiry = models.IntegerField(null=True, blank=True, help_text="Days until download expires")
    
    # Subscription Products
    subscription_period = models.CharField(max_length=20, choices=[('day', 'Daily'), ('week', 'Weekly'), ('month', 'Monthly'), ('year', 'Yearly')], blank=True)
    subscription_length = models.IntegerField(null=True, blank=True, help_text="Number of periods")
    trial_period = models.CharField(max_length=20, choices=[('day', 'Daily'), ('week', 'Weekly'), ('month', 'Monthly'), ('year', 'Yearly')], blank=True)
    trial_length = models.IntegerField(null=True, blank=True)
    
    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(max_length=500, blank=True)
    meta_keywords = models.TextField(blank=True)
    canonical_url = models.URLField(blank=True)
    focus_keyword = models.CharField(max_length=255, blank=True)
    
    # Reviews & Ratings
    enable_reviews = models.BooleanField(default=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    rating_count = models.PositiveIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    
    # Status & Visibility
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('pending', 'Pending Review'),
        ('private', 'Private'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ], default='draft', db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_bestseller = models.BooleanField(default=False, db_index=True)
    is_new = models.BooleanField(default=False, db_index=True)
    is_on_sale = models.BooleanField(default=False, db_index=True)
    
    # Visibility settings
    catalog_visibility = models.CharField(max_length=20, choices=[
        ('visible', 'Shop and Search'),
        ('catalog', 'Shop Only'),
        ('search', 'Search Only'),
        ('hidden', 'Hidden'),
    ], default='visible')
    
    # Purchase settings
    sold_individually = models.BooleanField(default=False, help_text="Limit to 1 per order")
    min_purchase_quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    max_purchase_quantity = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    
    # Analytics
    view_count = models.PositiveBigIntegerField(default=0)
    sales_count = models.PositiveBigIntegerField(default=0)
    
    # Dates
    available_from = models.DateTimeField(null=True, blank=True, db_index=True)
    available_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug', 'status', 'is_active']),
            models.Index(fields=['sku', 'is_active']),
            models.Index(fields=['product_type', 'status', 'is_active']),
            models.Index(fields=['-created_at', 'status', 'is_active']),
            models.Index(fields=['is_featured', 'status', 'is_active']),
            models.Index(fields=['is_on_sale', 'status', 'is_active']),
            models.Index(fields=['brand', 'status', 'is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    """Product images with advanced features"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    
    image = models.ImageField(upload_to='products/%Y/%m/')
    thumbnail = models.ImageField(upload_to='products/thumbnails/%Y/%m/', blank=True, null=True)
    alt_text = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True)
    
    # Organization
    is_primary = models.BooleanField(default=False, db_index=True)
    display_order = models.IntegerField(default=0)
    
    # Features
    is_zoom_enabled = models.BooleanField(default=True)
    show_in_gallery = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
        indexes = [
            models.Index(fields=['product', 'is_primary']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - Image {self.display_order}"


class ProductVideo(models.Model):
    """Product videos"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='videos')
    
    VIDEO_TYPES = [
        ('youtube', 'YouTube'),
        ('vimeo', 'Vimeo'),
        ('upload', 'Uploaded'),
        ('external', 'External URL'),
    ]
    
    video_type = models.CharField(max_length=20, choices=VIDEO_TYPES)
    video_url = models.URLField(blank=True)
    video_id = models.CharField(max_length=255, blank=True, help_text="YouTube/Vimeo video ID")
    video_file = models.FileField(upload_to='products/videos/%Y/%m/', blank=True, null=True)
    
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to='products/video_thumbs/%Y/%m/', blank=True, null=True)
    
    display_order = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
    
    def __str__(self):
        return f"{self.product.name} - Video {self.display_order}"


class ProductDocument(models.Model):
    """Product documents (manuals, certificates, etc.)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='documents')
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='products/documents/%Y/%m/', validators=[
        FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'zip'])
    ])
    file_size = models.PositiveBigIntegerField(default=0, help_text="Size in bytes")
    
    document_type = models.CharField(max_length=100, choices=[
        ('manual', 'User Manual'),
        ('datasheet', 'Datasheet'),
        ('certificate', 'Certificate'),
        ('warranty', 'Warranty'),
        ('guide', 'Guide'),
        ('other', 'Other'),
    ], default='other')
    
    is_downloadable = models.BooleanField(default=True)
    requires_login = models.BooleanField(default=False)
    
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
    
    def __str__(self):
        return f"{self.product.name} - {self.title}"


class ProductAttributeValue(models.Model):
    """Product-specific attribute values"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='attribute_values')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='product_values')
    
    # Value storage (only one will be used based on attribute type)
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_option = models.ForeignKey(AttributeValue, on_delete=models.SET_NULL, null=True, blank=True, related_name='product_assignments')
    value_json = models.JSONField(null=True, blank=True, help_text="For complex values")
    
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order']
        unique_together = [['product', 'attribute']]
    
    def __str__(self):
        return f"{self.product.name} - {self.attribute.name}"


# ============================================================================
# VARIANTS SYSTEM
# ============================================================================

class ProductVariant(models.Model):
    """
    Product variants (combinations of variant options).
    For variable products only.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    
    # Identification
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    barcode = models.CharField(max_length=100, blank=True, db_index=True)
    mpn = models.CharField(max_length=100, blank=True, help_text="Manufacturer Part Number")
    gtin = models.CharField(max_length=50, blank=True, help_text="Global Trade Item Number")
    
    # Variant name/title
    variant_name = models.CharField(max_length=255, blank=True)
    
    # Attributes that define this variant
    option_values = models.ManyToManyField(AttributeValue, related_name='variants', blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    
    # Inventory
    stock_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reserved_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)], help_text="Reserved in pending orders")
    available_quantity = models.GeneratedField(
        expression=models.F('stock_quantity') - models.F('reserved_quantity'),
        output_field=models.IntegerField(),
        db_persist=True
    )
    low_stock_threshold = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    
    # Physical properties
    weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    length = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    width = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    is_default = models.BooleanField(default=False, help_text="Default variant for product")
    
    # Analytics
    sales_count = models.PositiveBigIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['product', 'sku']
        indexes = [
            models.Index(fields=['sku', 'is_active']),
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['barcode']),
        ]
    
    def __str__(self):
        if self.variant_name:
            return f"{self.product.name} - {self.variant_name}"
        return f"{self.product.name} - {self.sku}"


class VariantImage(models.Model):
    """Images specific to product variants"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='images')
    
    image = models.ImageField(upload_to='variants/%Y/%m/')
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
    
    def __str__(self):
        return f"{self.variant} - Image {self.display_order}"


# ============================================================================
# PRICING: ADVANCED PRICING RULES
# ============================================================================

class PriceRule(models.Model):
    """
    Advanced pricing rules (tier pricing, customer group pricing, etc.)
    """
    RULE_TYPES = [
        ('tier', 'Tier Pricing (Quantity-based)'),
        ('customer_group', 'Customer Group Pricing'),
        ('schedule', 'Scheduled Pricing'),
        ('bundle', 'Bundle Pricing'),
        ('flash_sale', 'Flash Sale'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    rule_type = models.CharField(max_length=50, choices=RULE_TYPES)
    
    # Applicable to
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='price_rules')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True, related_name='price_rules')
    categories = models.ManyToManyField(Category, blank=True, related_name='price_rules')
    
    # Pricing
    price_type = models.CharField(max_length=20, choices=[
        ('fixed', 'Fixed Price'),
        ('percentage', 'Percentage Discount'),
        ('fixed_discount', 'Fixed Discount'),
    ])
    price_value = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Conditions
    min_quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    max_quantity = models.IntegerField(null=True, blank=True)
    customer_groups = models.JSONField(default=list, blank=True, help_text="List of customer group IDs")
    
    # Schedule
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    # Priority
    priority = models.IntegerField(default=0, help_text="Higher priority rules apply first")
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', 'name']
        indexes = [
            models.Index(fields=['rule_type', 'is_active']),
            models.Index(fields=['valid_from', 'valid_until', 'is_active']),
        ]
    
    def __str__(self):
        return self.name


# ============================================================================
# DISCOUNTS & PROMOTIONS: COMPREHENSIVE SYSTEM
# ============================================================================

class Promotion(models.Model):
    """
    Master promotion entity. Can include multiple types of discounts/offers.
    """
    PROMOTION_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed_amount', 'Fixed Amount Discount'),
        ('buy_x_get_y', 'Buy X Get Y'),
        ('bundle', 'Bundle Deal'),
        ('free_shipping', 'Free Shipping'),
        ('gift', 'Free Gift'),
        ('points_multiplier', 'Loyalty Points Multiplier'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    promotion_type = models.CharField(max_length=50, choices=PROMOTION_TYPES)
    
    # Display
    label = models.CharField(max_length=100, blank=True, help_text="Badge label (e.g., 'SALE', '50% OFF')")
    banner_image = models.ImageField(upload_to='promotions/%Y/%m/', blank=True, null=True)
    
    # Discount configuration
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Buy X Get Y configuration
    buy_quantity = models.IntegerField(null=True, blank=True)
    get_quantity = models.IntegerField(null=True, blank=True)
    get_discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Applicable to
    applies_to = models.CharField(max_length=20, choices=[
        ('all', 'All Products'),
        ('specific', 'Specific Products'),
        ('categories', 'Categories'),
        ('brands', 'Brands'),
        ('tags', 'Tags'),
    ], default='all')
    products = models.ManyToManyField(Product, blank=True, related_name='promotions')
    variants = models.ManyToManyField(ProductVariant, blank=True, related_name='promotions')
    categories = models.ManyToManyField(Category, blank=True, related_name='promotions')
    brands = models.ManyToManyField(Brand, blank=True, related_name='promotions')
    tags = models.ManyToManyField(Tag, blank=True, related_name='promotions')
    
    # Conditions
    min_purchase_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_purchase_quantity = models.IntegerField(null=True, blank=True)
    max_uses_total = models.IntegerField(null=True, blank=True)
    max_uses_per_customer = models.IntegerField(null=True, blank=True)
    
    # Customer restrictions
    customer_eligibility = models.CharField(max_length=20, choices=[
        ('all', 'All Customers'),
        ('new', 'New Customers Only'),
        ('existing', 'Existing Customers'),
        ('groups', 'Specific Customer Groups'),
    ], default='all')
    customer_groups = models.JSONField(default=list, blank=True)
    
    # Stacking
    can_stack_with_coupons = models.BooleanField(default=True)
    can_stack_with_promotions = models.BooleanField(default=True)
    
    # Schedule
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    # Priority
    priority = models.IntegerField(default=0)
    
    # Status & tracking
    is_active = models.BooleanField(default=True, db_index=True)
    use_count = models.PositiveBigIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', '-starts_at']
        indexes = [
            models.Index(fields=['promotion_type', 'is_active']),
            models.Index(fields=['starts_at', 'ends_at', 'is_active']),
        ]
    
    def __str__(self):
        return self.name


class Coupon(models.Model):
    """
    Coupon/voucher codes that customers can redeem.
    """
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed_cart', 'Fixed Cart Discount'),
        ('fixed_product', 'Fixed Product Discount'),
        ('free_shipping', 'Free Shipping'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    
    # Discount configuration
    discount_type = models.CharField(max_length=50, choices=DISCOUNT_TYPES)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    max_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Applicable to
    applies_to = models.CharField(max_length=20, choices=[
        ('cart', 'Entire Cart'),
        ('products', 'Specific Products'),
        ('categories', 'Categories'),
    ], default='cart')
    products = models.ManyToManyField(Product, blank=True, related_name='coupons')
    categories = models.ManyToManyField(Category, blank=True, related_name='coupons')
    excluded_products = models.ManyToManyField(Product, blank=True, related_name='excluded_from_coupons')
    excluded_categories = models.ManyToManyField(Category, blank=True, related_name='excluded_from_coupons')
    
    # Conditions
    min_purchase_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_purchase_quantity = models.IntegerField(null=True, blank=True)
    
    # Usage limits
    usage_limit_total = models.IntegerField(null=True, blank=True, help_text="Total times this coupon can be used")
    usage_limit_per_customer = models.IntegerField(default=1)
    usage_count = models.PositiveIntegerField(default=0)
    
    # Customer restrictions
    customer_eligibility = models.CharField(max_length=20, choices=[
        ('all', 'All Customers'),
        ('new', 'New Customers Only'),
        ('specific', 'Specific Customers'),
    ], default='all')
    allowed_users = models.ManyToManyField(User, blank=True, related_name='allowed_coupons')
    
    # Validity
    valid_from = models.DateTimeField(db_index=True)
    valid_until = models.DateTimeField(null=True, blank=True, db_index=True)
    
    # Additional rules
    individual_use = models.BooleanField(default=False, help_text="Cannot be combined with other coupons")
    exclude_sale_items = models.BooleanField(default=False)
    free_shipping = models.BooleanField(default=False)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code', 'is_active']),
            models.Index(fields=['valid_from', 'valid_until', 'is_active']),
        ]
    
    def __str__(self):
        return self.code


class CouponUsage(models.Model):
    """Track coupon usage"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coupon_usages')
    order_id = models.UUIDField(db_index=True)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2)
    used_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-used_at']
        indexes = [
            models.Index(fields=['coupon', 'user']),
            models.Index(fields=['order_id']),
        ]
    
    def __str__(self):
        return f"{self.user} used {self.coupon.code}"


# ============================================================================
# BUNDLES & GROUPED PRODUCTS
# ============================================================================

class ProductBundle(models.Model):
    """Product bundles (buy together deals)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bundles')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Pricing
    bundle_type = models.CharField(max_length=20, choices=[
        ('fixed', 'Fixed Bundle Price'),
        ('discount', 'Percentage Discount'),
        ('dynamic', 'Sum of Prices'),
    ], default='discount')
    bundle_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Configuration
    is_optional = models.BooleanField(default=False, help_text="Customer can choose to buy bundle or not")
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.parent_product.name} - {self.name}"


class BundleItem(models.Model):
    """Items included in a bundle"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bundle = models.ForeignKey(ProductBundle, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)
    
    quantity = models.PositiveIntegerField(default=1)
    is_optional = models.BooleanField(default=False)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order']
    
    def __str__(self):
        product_name = self.variant.product.name if self.variant else self.product.name
        return f"{self.bundle.name} - {product_name} x{self.quantity}"


class GroupedProduct(models.Model):
    """Grouped products (product families shown together)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='grouped_products')
    child_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='part_of_groups')
    
    default_quantity = models.PositiveIntegerField(default=1)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order']
        unique_together = [['parent_product', 'child_product']]
    
    def __str__(self):
        return f"{self.parent_product.name} includes {self.child_product.name}"


# ============================================================================
# CONTINUE IN NEXT MESSAGE...
# ============================================================================
"""
ENTERPRISE E-COMMERCE MODELS - PART 2
=====================================
Reviews, Inventory, Digital Products, Gift Cards, Subscriptions, Loyalty, Analytics
"""

# Continue from Part 1...

# ============================================================================
# REVIEWS & RATINGS SYSTEM
# ============================================================================

class Review(models.Model):
    """Comprehensive product review system"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    
    # Review content
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], db_index=True)
    title = models.CharField(max_length=255)
    review_text = models.TextField()
    
    # Detailed ratings (optional)
    quality_rating = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    value_rating = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    shipping_rating = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    
    # Pros and Cons
    pros = models.JSONField(default=list, blank=True, help_text="List of pros")
    cons = models.JSONField(default=list, blank=True, help_text="List of cons")
    
    # Metadata
    is_verified_purchase = models.BooleanField(default=False, db_index=True)
    order_id = models.UUIDField(null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    
    # Moderation
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending Moderation'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('spam', 'Marked as Spam'),
    ], default='pending', db_index=True)
    moderation_note = models.TextField(blank=True)
    moderated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_reviews')
    moderated_at = models.DateTimeField(null=True, blank=True)
    
    # Engagement
    helpful_count = models.PositiveIntegerField(default=0)
    not_helpful_count = models.PositiveIntegerField(default=0)
    report_count = models.PositiveIntegerField(default=0)
    
    # Seller response
    seller_response = models.TextField(blank=True)
    seller_responded_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = [['product', 'user']]
        indexes = [
            models.Index(fields=['product', 'status', 'rating']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['-created_at', 'status']),
            models.Index(fields=['is_verified_purchase', 'status']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.rating}⭐ by {self.user}"


class ReviewImage(models.Model):
    """Images attached to reviews"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='reviews/%Y/%m/')
    caption = models.CharField(max_length=255, blank=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
    
    def __str__(self):
        return f"Review Image for {self.review.product.name}"


class ReviewVideo(models.Model):
    """Videos attached to reviews"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='videos')
    video_file = models.FileField(upload_to='reviews/videos/%Y/%m/', blank=True, null=True)
    video_url = models.URLField(blank=True)
    thumbnail = models.ImageField(upload_to='reviews/video_thumbs/%Y/%m/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Review Video for {self.review.product.name}"


class ReviewHelpful(models.Model):
    """Track helpful votes on reviews"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='helpful_votes')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_helpful = models.BooleanField(help_text="True=Helpful, False=Not Helpful")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['review', 'user']]
    
    def __str__(self):
        return f"{self.user} found review {'helpful' if self.is_helpful else 'not helpful'}"


class ReviewReport(models.Model):
    """Report inappropriate reviews"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='reports')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reason = models.CharField(max_length=50, choices=[
        ('spam', 'Spam'),
        ('inappropriate', 'Inappropriate Content'),
        ('fake', 'Fake Review'),
        ('offensive', 'Offensive Language'),
        ('other', 'Other'),
    ])
    details = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('action_taken', 'Action Taken'),
        ('dismissed', 'Dismissed'),
    ], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['review', 'user']]
    
    def __str__(self):
        return f"Report on {self.review.product.name} review"


class QA(models.Model):
    """Product Questions & Answers"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='questions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='questions')
    
    question = models.TextField()
    
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', db_index=True)
    
    helpful_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Q: {self.question[:50]}..."


class QAAnswer(models.Model):
    """Answers to product questions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(QA, on_delete=models.CASCADE, related_name='answers')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='answers')
    
    answer = models.TextField()
    is_seller_answer = models.BooleanField(default=False)
    is_verified_buyer = models.BooleanField(default=False)
    
    helpful_count = models.PositiveIntegerField(default=0)
    
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Answer'
        ordering = ['-is_seller_answer', '-helpful_count', '-created_at']
    
    def __str__(self):
        return f"A: {self.answer[:50]}..."


# ============================================================================
# INVENTORY MANAGEMENT
# ============================================================================

class Warehouse(models.Model):
    """Warehouse/fulfillment centers"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    
    # Address
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=2)
    
    # Contact
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    
    # Settings
    is_active = models.BooleanField(default=True, db_index=True)
    is_default = models.BooleanField(default=False)
    priority = models.IntegerField(default=0, help_text="Order of selection")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['priority', 'name']
    
    def __str__(self):
        return self.name


class InventoryLocation(models.Model):
    """Track inventory by warehouse and location"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='inventory')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='inventory_locations')
    
    # Location within warehouse
    zone = models.CharField(max_length=50, blank=True)
    aisle = models.CharField(max_length=50, blank=True)
    rack = models.CharField(max_length=50, blank=True)
    bin = models.CharField(max_length=50, blank=True)
    
    # Stock levels
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reserved_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    available_quantity = models.GeneratedField(
        expression=models.F('quantity') - models.F('reserved_quantity'),
        output_field=models.IntegerField(),
        db_persist=True
    )
    
    # Thresholds
    reorder_point = models.IntegerField(default=10)
    reorder_quantity = models.IntegerField(default=50)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    last_counted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['warehouse', 'variant']]
        indexes = [
            models.Index(fields=['warehouse', 'variant', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.variant.sku} @ {self.warehouse.code}"


class StockMovement(models.Model):
    """Track all stock movements (audit trail)"""
    MOVEMENT_TYPES = [
        ('purchase', 'Purchase Order'),
        ('sale', 'Sale'),
        ('return', 'Return'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Transfer'),
        ('damage', 'Damage/Loss'),
        ('found', 'Found'),
        ('recount', 'Recount'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='stock_movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock_movements')
    
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, db_index=True)
    quantity = models.IntegerField(help_text="Positive for additions, negative for deductions")
    
    # Previous and new quantities
    quantity_before = models.IntegerField()
    quantity_after = models.IntegerField()
    
    # Reference
    reference_type = models.CharField(max_length=50, blank=True, help_text="order, transfer, adjustment, etc.")
    reference_id = models.UUIDField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Who did it
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['variant', '-created_at']),
            models.Index(fields=['warehouse', '-created_at']),
            models.Index(fields=['movement_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_movement_type_display()}: {self.variant.sku} ({self.quantity:+d})"


# ============================================================================
# DIGITAL PRODUCTS & DOWNLOADS
# ============================================================================

class DigitalProduct(models.Model):
    """Digital/downloadable products"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='digital_product')
    
    # File storage
    file = models.FileField(upload_to='digital_products/%Y/%m/', blank=True, null=True)
    file_url = models.URLField(blank=True, help_text="External file URL")
    file_size = models.BigIntegerField(default=0, help_text="Size in bytes")
    file_type = models.CharField(max_length=100, blank=True)
    
    # Download settings
    download_limit = models.IntegerField(null=True, blank=True, help_text="Max downloads per purchase (null=unlimited)")
    download_expiry_days = models.IntegerField(null=True, blank=True, help_text="Days until download expires (null=never)")
    
    # Version control
    version = models.CharField(max_length=50, blank=True)
    release_notes = models.TextField(blank=True)
    
    # License
    license_type = models.CharField(max_length=100, blank=True)
    license_text = models.TextField(blank=True)
    requires_license_key = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Digital: {self.product.name}"


class DownloadLog(models.Model):
    """Track download activity"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    digital_product = models.ForeignKey(DigitalProduct, on_delete=models.CASCADE, related_name='downloads')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='downloads')
    order_id = models.UUIDField(db_index=True)
    
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    download_count = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    first_downloaded_at = models.DateTimeField(auto_now_add=True)
    last_downloaded_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'order_id']),
            models.Index(fields=['digital_product', 'user']),
        ]
    
    def __str__(self):
        return f"{self.user} downloaded {self.digital_product.product.name}"


# ============================================================================
# GIFT CARDS
# ============================================================================

class GiftCard(models.Model):
    """Gift card/voucher system"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Value
    initial_value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    current_value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='USD')
    
    # Recipient
    recipient_email = models.EmailField(blank=True)
    recipient_name = models.CharField(max_length=255, blank=True)
    message = models.TextField(blank=True)
    
    # Sender (if gift)
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_gift_cards')
    purchased_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchased_gift_cards')
    
    # Usage
    used_by = models.ManyToManyField(User, through='GiftCardUsage', related_name='used_gift_cards')
    
    # Validity
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('active', 'Active'),
        ('partially_used', 'Partially Used'),
        ('used', 'Fully Used'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='active', db_index=True)
    
    # Design
    design_template = models.CharField(max_length=100, blank=True)
    custom_image = models.ImageField(upload_to='gift_cards/%Y/%m/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Gift Card {self.code} - ${self.current_value}"


class GiftCardUsage(models.Model):
    """Track gift card usage"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gift_card = models.ForeignKey(GiftCard, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order_id = models.UUIDField(db_index=True)
    
    amount_used = models.DecimalField(max_digits=12, decimal_places=2)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    
    used_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-used_at']
    
    def __str__(self):
        return f"{self.gift_card.code} - ${self.amount_used} used"


# ============================================================================
# SUBSCRIPTIONS
# ============================================================================

class SubscriptionPlan(models.Model):
    """Subscription product plans"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='subscription_plans')
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Billing
    billing_period = models.CharField(max_length=20, choices=[
        ('day', 'Daily'),
        ('week', 'Weekly'),
        ('month', 'Monthly'),
        ('year', 'Yearly'),
    ])
    billing_interval = models.IntegerField(default=1, help_text="Bill every X periods")
    
    # Price
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    setup_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Trial
    trial_period = models.CharField(max_length=20, choices=[
        ('day', 'Daily'),
        ('week', 'Weekly'),
        ('month', 'Monthly'),
    ], blank=True)
    trial_interval = models.IntegerField(default=0)
    trial_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Limits
    subscription_length = models.IntegerField(null=True, blank=True, help_text="Total billing cycles (null=indefinite)")
    
    # Features
    features = models.JSONField(default=list, blank=True)
    
    is_active = models.BooleanField(default=True, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['price']
    
    def __str__(self):
        return f"{self.product.name} - {self.name}"


# ============================================================================
# LOYALTY & REWARDS
# ============================================================================

class LoyaltyProgram(models.Model):
    """Loyalty/rewards program configuration"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Points earning
    points_per_dollar = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    points_per_order = models.IntegerField(default=0)
    signup_bonus_points = models.IntegerField(default=0)
    referral_bonus_points = models.IntegerField(default=0)
    
    # Points redemption
    points_value = models.DecimalField(max_digits=10, decimal_places=4, help_text="Dollar value of 1 point")
    min_points_to_redeem = models.IntegerField(default=100)
    max_points_per_order = models.IntegerField(null=True, blank=True)
    
    # Expiry
    points_expiry_days = models.IntegerField(null=True, blank=True, help_text="Days until points expire (null=never)")
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class LoyaltyAccount(models.Model):
    """User loyalty account"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='loyalty_account')
    program = models.ForeignKey(LoyaltyProgram, on_delete=models.CASCADE, related_name='accounts')
    
    # Balance
    points_balance = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    lifetime_points_earned = models.IntegerField(default=0)
    lifetime_points_spent = models.IntegerField(default=0)
    
    # Tier (optional)
    tier = models.CharField(max_length=50, blank=True)
    tier_progress = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user} - {self.points_balance} points"


class LoyaltyTransaction(models.Model):
    """Loyalty points transactions"""
    TRANSACTION_TYPES = [
        ('earn_purchase', 'Earned from Purchase'),
        ('earn_signup', 'Signup Bonus'),
        ('earn_referral', 'Referral Bonus'),
        ('earn_review', 'Review Reward'),
        ('earn_birthday', 'Birthday Bonus'),
        ('earn_manual', 'Manual Addition'),
        ('redeem', 'Redeemed'),
        ('expire', 'Expired'),
        ('refund', 'Refunded'),
        ('adjust', 'Adjustment'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(LoyaltyAccount, on_delete=models.CASCADE, related_name='transactions')
    
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPES)
    points = models.IntegerField(help_text="Positive for earning, negative for spending")
    
    balance_before = models.IntegerField()
    balance_after = models.IntegerField()
    
    # Reference
    order_id = models.UUIDField(null=True, blank=True, db_index=True)
    reference_id = models.UUIDField(null=True, blank=True)
    
    description = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.account.user} - {self.points:+d} points"


# ============================================================================
# WISHLISTS & FAVORITES
# ============================================================================

class Wishlist(models.Model):
    """User wishlists (can have multiple)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlists')
    
    name = models.CharField(max_length=255, default='My Wishlist')
    description = models.TextField(blank=True)
    
    # Privacy
    is_public = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user} - {self.name}"


class WishlistItem(models.Model):
    """Items in wishlist"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)
    
    quantity = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    priority = models.IntegerField(default=0)
    
    added_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-priority', '-added_at']
        unique_together = [['wishlist', 'product', 'variant']]
    
    def __str__(self):
        return f"{self.wishlist.user} - {self.product.name}"


# ============================================================================
# PRODUCT ANALYTICS & TRACKING
# ============================================================================

class ProductView(models.Model):
    """Track product views for analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='views')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session_key = models.CharField(max_length=100, db_index=True)
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    referrer = models.URLField(blank=True)
    
    # Location (if available)
    country = models.CharField(max_length=2, blank=True)
    city = models.CharField(max_length=100, blank=True)
    
    viewed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-viewed_at']
        indexes = [
            models.Index(fields=['product', '-viewed_at']),
            models.Index(fields=['user', '-viewed_at']),
            models.Index(fields=['session_key', '-viewed_at']),
        ]
    
    def __str__(self):
        return f"{self.product.name} viewed at {self.viewed_at}"


class ProductSearch(models.Model):
    """Track search queries"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.CharField(max_length=500, db_index=True)
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session_key = models.CharField(max_length=100, db_index=True)
    
    results_count = models.IntegerField(default=0)
    clicked_product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='search_clicks')
    
    searched_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        verbose_name_plural = 'Product Searches'
        ordering = ['-searched_at']
        indexes = [
            models.Index(fields=['query', '-searched_at']),
        ]
    
    def __str__(self):
        return f"Search: {self.query}"


class ProductComparison(models.Model):
    """Track product comparisons"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session_key = models.CharField(max_length=100, db_index=True)
    
    products = models.ManyToManyField(Product, related_name='comparisons')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Comparison by {self.user or self.session_key}"


# ============================================================================
# SEO & REDIRECTS
# ============================================================================

class URLRedirect(models.Model):
    """Manage URL redirects (for changed product URLs, etc.)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    old_path = models.CharField(max_length=500, unique=True, db_index=True)
    new_path = models.CharField(max_length=500)
    
    redirect_type = models.IntegerField(choices=[
        (301, 'Permanent (301)'),
        (302, 'Temporary (302)'),
    ], default=301)
    
    is_active = models.BooleanField(default=True, db_index=True)
    
    hit_count = models.PositiveBigIntegerField(default=0)
    last_hit_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.old_path} → {self.new_path}"
