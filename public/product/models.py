from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from decimal import Decimal
import uuid
from public.category.models import Category, Tag, Brand
from dashboard.settings.models import AuditModel, TenantUser as User

# User = get_user_model()


class AttributeGroup(AuditModel):
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


class Attribute(AuditModel):
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
    attribute_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default='text')
    group = models.ForeignKey(AttributeGroup, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='attributes')

    # Configuration
    description = models.TextField(blank=True)
    help_text = models.CharField(max_length=255, blank=True)
    unit = models.CharField(max_length=50, blank=True,
                            help_text="e.g., cm, kg, etc.")

    # Validation
    is_required = models.BooleanField(default=False)
    is_unique = models.BooleanField(default=False)
    min_value = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True)
    regex_pattern = models.CharField(max_length=500, blank=True)

    # Usage
    is_variant_option = models.BooleanField(
        default=False, help_text="Used to create variants")
    is_filterable = models.BooleanField(
        default=True, help_text="Show in filters")
    is_searchable = models.BooleanField(
        default=True, help_text="Include in search")
    is_comparable = models.BooleanField(
        default=True, help_text="Show in comparison")

    # Display
    display_order = models.IntegerField(default=0)
    is_visible_on_front = models.BooleanField(default=False)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class AttributeValue(AuditModel):
    """Predefined values for select-type attributes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attribute = models.ForeignKey(
        Attribute, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, db_index=True)

    # Visual representation
    color_hex = models.CharField(
        max_length=7, blank=True, help_text="For color attributes")
    image = models.ImageField(
        upload_to='attributes/%Y/%m/', blank=True, null=True)
    swatch = models.ImageField(
        upload_to='attributes/swatches/%Y/%m/', blank=True, null=True)

    # Additional data
    description = models.TextField(blank=True)
    extra_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Additional cost")

    # Display
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

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
# =======================================================kkkkkkkkkkjjiii=====================

class Product(AuditModel):
    """
    Main product entity. Can have multiple variants.
    Think of this as the "product family".
    """
    TYPE_CHOICES = [
        ('simple', 'Simple Product'),
        ('variable', 'Variable Product (has variants)'),
        # ('grouped', 'Grouped Product'),
        # ('bundle', 'Bundle'),
        # ('subscription', 'Subscription'),
        # ('digital', 'Digital/Downloadable'),
        # ('service', 'Service'),
        # ('rental', 'Rental'),
        # ('gift_card', 'Gift Card'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic Info
    name = models.CharField(max_length=500, db_index=True)
    slug = models.SlugField(max_length=500, unique=True, db_index=True)
    sku = models.CharField(max_length=100, unique=True,
                           db_index=True, help_text="Stock Keeping Unit")

    # Type & Classification
    product_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default='simple', db_index=True)
    categories = models.ManyToManyField(
        Category, related_name='products', blank=True)
    tags = models.ManyToManyField(Tag, related_name='products', blank=True)
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    # Content
    short_description = models.TextField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    specifications = models.JSONField(
        default=dict, blank=True, help_text="Technical specs as JSON")
    features = models.JSONField(
        default=list, blank=True, help_text="Feature list as JSON array")

    # Pricing (for simple products, variants override these)
    price = models.DecimalField(max_digits=12, decimal_places=2,
                                null=True, blank=True, validators=[MinValueValidator(0)])
    compare_at_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])

    # Tax
    tax_class = models.CharField(max_length=100, blank=True)
    tax_status = models.CharField(max_length=20, choices=[(
        'taxable', 'Taxable'), ('shipping', 'Shipping Only'), ('none', 'None')], default='taxable')

    # Inventory (for simple products)
    manage_stock = models.BooleanField(default=True)  # ===
    stock_quantity = models.IntegerField(
        default=0, validators=[MinValueValidator(0)])
    stock_status = models.CharField(max_length=20, choices=[('in_stock', 'In Stock'), (
        'out_of_stock', 'Out of Stock'), ('on_backorder', 'On Backorder')], default='in_stock', db_index=True)
    low_stock_threshold = models.IntegerField(
        default=5, validators=[MinValueValidator(0)])
    backorders_allowed = models.BooleanField(default=False)  # ===

    # Shipping
    requires_shipping = models.BooleanField(default=True)
    weight = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True, help_text="Weight in kg")
    length = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Length in cm")
    width = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Width in cm")
    height = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Height in cm")

    # Digital Products
    # is_downloadable = models.BooleanField(default=False)
    # download_limit = models.IntegerField(null=True, blank=True, help_text="Max downloads per purchase")
    # download_expiry = models.IntegerField(null=True, blank=True, help_text="Days until download expires")

    # # Subscription Products
    # subscription_period = models.CharField(max_length=20, choices=[('day', 'Daily'), ('week', 'Weekly'), ('month', 'Monthly'), ('year', 'Yearly')], blank=True)
    # subscription_length = models.IntegerField(null=True, blank=True, help_text="Number of periods")
    # trial_period = models.CharField(max_length=20, choices=[('day', 'Daily'), ('week', 'Weekly'), ('month', 'Monthly'), ('year', 'Yearly')], blank=True)
    # trial_length = models.IntegerField(null=True, blank=True)

    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(max_length=500, blank=True)
    meta_keywords = models.TextField(blank=True)
    canonical_url = models.URLField(blank=True)
    focus_keyword = models.CharField(max_length=255, blank=True)

    # Reviews & Ratings
    enable_reviews = models.BooleanField(default=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, validators=[
                                         MinValueValidator(0), MaxValueValidator(5)])
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

    # Analytics
    view_count = models.PositiveBigIntegerField(default=0)
    sales_count = models.PositiveBigIntegerField(default=0)
    is_pos_available = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Allow this catalog product to be bridged into the POS catalog.",
    )

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
        if not self.slug and self.name:
            base_slug = slugify(self.name)
            if not base_slug:
                import uuid
                base_slug = f'product-{str(uuid.uuid4())[:8]}'

            # Check for uniqueness
            counter = 1
            unique_slug = base_slug
            while Product.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = unique_slug
        elif not self.slug:
            import uuid
            self.slug = f'product-{str(uuid.uuid4())[:8]}'

        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class ProductImage(AuditModel):
    """Product images with advanced features"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='images')

    image = models.ImageField(upload_to='products/%Y/%m/')
    caption = models.TextField(blank=True)  # ❌❌

    # Organization
    is_primary = models.BooleanField(default=False, db_index=True)
    display_order = models.IntegerField(default=0)

    # Features
    is_zoom_enabled = models.BooleanField(default=True)
    show_in_gallery = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'created_at']
        indexes = [
            models.Index(fields=['product', 'is_primary']),
        ]

    def __str__(self):
        return f"{self.product.name} - Image {self.display_order}"


class ProductVideo(AuditModel):
    """Product videos"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='videos')

    VIDEO_TYPES = [
        ('youtube', 'YouTube'),
        ('vimeo', 'Vimeo'),
        ('upload', 'Uploaded'),
        ('external', 'External URL'),
    ]

    video_type = models.CharField(max_length=20, choices=VIDEO_TYPES)  # ❌❌
    video_url = models.URLField(blank=True)
    video_id = models.CharField(
        max_length=255, blank=True, help_text="YouTube/Vimeo video ID")
    video_file = models.FileField(
        upload_to='products/videos/%Y/%m/', blank=True, null=True)

    title = models.CharField(max_length=255, blank=True)  # ❌❌
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(
        upload_to='products/video_thumbs/%Y/%m/', blank=True, null=True)

    display_order = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'created_at']

    def __str__(self):
        return f"{self.product.name} - Video {self.display_order}"


# class ProductDocument(AuditModel):  # ❌❌
#     """Product documents (manuals, certificates, etc.)"""
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='documents')

#     title = models.CharField(max_length=255)
#     description = models.TextField(blank=True)
#     file = models.FileField(upload_to='products/documents/%Y/%m/', validators=[
#         FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'zip'])
#     ])
#     file_size = models.PositiveBigIntegerField(default=0, help_text="Size in bytes")

#     document_type = models.CharField(max_length=100, choices=[
#         ('manual', 'User Manual'),
#         ('datasheet', 'Datasheet'),
#         ('certificate', 'Certificate'),
#         ('warranty', 'Warranty'),
#         ('guide', 'Guide'),
#         ('other', 'Other'),
#     ], default='other')

#     is_downloadable = models.BooleanField(default=True)
#     requires_login = models.BooleanField(default=False)

#     display_order = models.IntegerField(default=0)
#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ['display_order', 'created_at']

#     def __str__(self):
#         return f"{self.product.name} - {self.title}"


class ProductAttributeValue(AuditModel):
    """Product-specific attribute values"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='attribute_values')
    attribute = models.ForeignKey(
        Attribute, on_delete=models.CASCADE, related_name='product_values')

    # Value storage (only one will be used based on attribute type)
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_option = models.ForeignKey(
        AttributeValue, on_delete=models.SET_NULL, null=True, blank=True, related_name='product_assignments')
    value_json = models.JSONField(
        null=True, blank=True, help_text="For complex values")

    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order']
        unique_together = [['product', 'attribute']]

    def __str__(self):
        return f"{self.product.name} - {self.attribute.name}"


# ============================================================================
# VARIANTS SYSTEM
# ============================================================================

class ProductVariant(AuditModel):
    """
    Product variants (combinations of variant options).
    For variable products only.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='variants')

    # Identification
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    barcode = models.CharField(max_length=100, blank=True, db_index=True)  # ❌❌
    mpn = models.CharField(max_length=100, blank=True,
                           help_text="Manufacturer Part Number")  # ❌❌
    gtin = models.CharField(max_length=50, blank=True,
                            help_text="Global Trade Item Number")  # ❌❌

    # Variant name/title
    variant_name = models.CharField(max_length=255, blank=True)

    # Attributes that define this variant
    option_values = models.ManyToManyField(
        AttributeValue, related_name='variants', blank=True)

    # Pricing
    price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    compare_at_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])

    # Inventory
    stock_quantity = models.IntegerField(
        default=0, validators=[MinValueValidator(0)])
    reserved_quantity = models.IntegerField(default=0, validators=[
                                            MinValueValidator(0)], help_text="Reserved in pending orders")
    available_quantity = models.GeneratedField(
        expression=models.F('stock_quantity') - models.F('reserved_quantity'),
        output_field=models.IntegerField(),
        db_persist=True
    )
    low_stock_threshold = models.IntegerField(
        default=5, validators=[MinValueValidator(0)])

    # Physical properties
    weight = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True)
    length = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)
    width = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    is_default = models.BooleanField(
        default=False, help_text="Default variant for product")
    is_pos_available = models.BooleanField(
        default=True,
        db_index=True,
        help_text="If enabled and the parent product is POS-ready, this variant can be sold in POS.",
    )

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


class VariantImage(AuditModel):
    """Images specific to product variants"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name='images')

    image = models.ImageField(upload_to='variants/%Y/%m/')
    is_primary = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'created_at']

    def __str__(self):
        return f"{self.variant} - Image {self.display_order}"
