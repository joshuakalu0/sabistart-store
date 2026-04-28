from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class ProductPageSettings(models.Model):
    """
    Control individual product page layout and features.
    
    CONTROLS:
    - Product page layout and structure
    - Image gallery configuration
    - Variant display options
    - Add to cart behavior
    - Related products and recommendations
    - Trust signals and badges
    
    IMPACT:
    - Product detail page appearance
    - Conversion optimization
    - User experience on product pages
    
    SHOPIFY EQUIVALENT: Theme > Product pages
    """
    
    # === LAYOUT ===
    LAYOUT_CHOICES = [
        ('standard', 'Standard (Image Left, Details Right)'),
        ('wide', 'Wide Layout (Full Width)'),
        ('sticky', 'Sticky Add to Cart'),
        ('gallery', 'Gallery Focus (Large Images)'),
        ('minimal', 'Minimal (Clean Layout)'),
    ]
    layout = models.CharField(
        max_length=20,
        choices=LAYOUT_CHOICES,
        default='standard',
        help_text="Product page layout style"
    )
    
    # === IMAGE GALLERY ===
    gallery_style = models.CharField(
        max_length=20,
        choices=[
            ('thumbnails', 'Thumbnails Below'),
            ('thumbnails_side', 'Thumbnails on Side'),
            ('dots', 'Dot Navigation'),
            ('slider', 'Full Width Slider'),
            ('grid', 'Grid Gallery'),
        ],
        default='thumbnails',
        help_text="Image gallery navigation style"
    )
    
    enable_image_zoom = models.BooleanField(
        default=True,
        help_text="Enable zoom on hover/click"
    )
    
    enable_lightbox = models.BooleanField(
        default=True,
        help_text="Open images in lightbox/modal"
    )
    
    enable_360_view = models.BooleanField(
        default=False,
        help_text="Enable 360-degree product view"
    )
    
    enable_video_in_gallery = models.BooleanField(
        default=True,
        help_text="Allow product videos in gallery"
    )
    
    image_aspect_ratio = models.CharField(
        max_length=20,
        choices=[
            ('square', 'Square (1:1)'),
            ('portrait', 'Portrait (3:4)'),
            ('landscape', 'Landscape (4:3)'),
            ('auto', 'Original Ratio'),
        ],
        default='square'
    )
    
    # === PRODUCT INFO ===
    show_vendor = models.BooleanField(
        default=True,
        help_text="Show brand/vendor name"
    )
    
    show_sku = models.BooleanField(
        default=True,
        help_text="Show product SKU"
    )
    
    show_availability = models.BooleanField(
        default=True,
        help_text="Show stock availability status"
    )
    
    show_stock_quantity = models.BooleanField(
        default=False,
        help_text="Show exact stock count (e.g., '5 left in stock')"
    )
    
    low_stock_threshold = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Show 'low stock' warning below this quantity"
    )
    
    show_product_type = models.BooleanField(
        default=True,
        help_text="Show product category/type"
    )
    
    show_tags = models.BooleanField(
        default=True,
        help_text="Show product tags"
    )
    
    show_share_buttons = models.BooleanField(
        default=True,
        help_text="Show social sharing buttons"
    )
    
    # === VARIANTS ===
    variant_display = models.CharField(
        max_length=20,
        choices=[
            ('dropdown', 'Dropdown Select'),
            ('buttons', 'Button Pills'),
            ('swatches', 'Color Swatches'),
            ('images', 'Image Swatches'),
            ('radio', 'Radio Buttons'),
        ],
        default='buttons',
        help_text="How to display product variants"
    )
    
    show_variant_images = models.BooleanField(
        default=True,
        help_text="Change main image when variant selected"
    )
    
    show_variant_prices = models.BooleanField(
        default=True,
        help_text="Update price when variant selected"
    )
    
    # === PRICING ===
    show_price_per_unit = models.BooleanField(
        default=False,
        help_text="Show unit price (e.g., $5.99/kg)"
    )
    
    show_savings_amount = models.BooleanField(
        default=True,
        help_text="Show 'Save $10' on sale items"
    )
    
    show_savings_percentage = models.BooleanField(
        default=True,
        help_text="Show 'Save 20%' on sale items"
    )
    
    show_bulk_pricing = models.BooleanField(
        default=False,
        help_text="Show bulk/tiered pricing table"
    )
    
    show_tax_info = models.BooleanField(
        default=True,
        help_text="Show tax information (e.g., 'Tax included')"
    )
    
    # === QUANTITY SELECTOR ===
    quantity_selector_style = models.CharField(
        max_length=20,
        choices=[
            ('input', 'Number Input'),
            ('buttons', 'Plus/Minus Buttons'),
            ('dropdown', 'Dropdown'),
            ('stepper', 'Stepper Control'),
        ],
        default='buttons'
    )
    
    min_quantity = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Minimum order quantity"
    )
    
    max_quantity = models.IntegerField(
        default=999,
        validators=[MinValueValidator(1)],
        help_text="Maximum order quantity"
    )
    
    quantity_increments = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Quantity step increment"
    )
    
    # === ADD TO CART ===
    add_to_cart_button_text = models.CharField(
        max_length=50,
        default='Add to Cart'
    )
    
    show_buy_now_button = models.BooleanField(
        default=False,
        help_text="Show 'Buy Now' button (skip cart, go to checkout)"
    )
    
    buy_now_button_text = models.CharField(
        max_length=50,
        default='Buy Now'
    )
    
    enable_sticky_add_to_cart = models.BooleanField(
        default=True,
        help_text="Sticky add to cart bar on scroll"
    )
    
    show_quantity_in_sticky_bar = models.BooleanField(
        default=True,
        help_text="Show quantity selector in sticky bar"
    )
    
    # === TABS/ACCORDION ===
    description_display = models.CharField(
        max_length=20,
        choices=[
            ('tabs', 'Tabs'),
            ('accordion', 'Accordion'),
            ('full', 'Full Content (No Tabs)'),
            ('sidebar', 'Sidebar'),
        ],
        default='tabs'
    )
    
    show_description_tab = models.BooleanField(default=True)
    show_specifications_tab = models.BooleanField(default=True)
    show_shipping_tab = models.BooleanField(default=True)
    show_reviews_tab = models.BooleanField(default=True)
    show_questions_tab = models.BooleanField(default=False)
    
    # === TRUST SIGNALS ===
    show_trust_badges = models.BooleanField(
        default=True,
        help_text="Show trust badges (secure checkout, money-back, etc.)"
    )
    
    show_secure_checkout_badge = models.BooleanField(default=True)
    show_money_back_guarantee = models.BooleanField(default=False)
    show_free_shipping_badge = models.BooleanField(default=True)
    show_warranty_info = models.BooleanField(default=False)
    
    trust_badge_position = models.CharField(
        max_length=20,
        choices=[
            ('below_cart', 'Below Add to Cart'),
            ('above_cart', 'Above Add to Cart'),
            ('sidebar', 'In Sidebar'),
            ('footer', 'Page Footer'),
        ],
        default='below_cart'
    )
    
    # === RELATED PRODUCTS ===
    show_related_products = models.BooleanField(
        default=True,
        help_text="Show related/recommended products"
    )
    
    related_products_title = models.CharField(
        max_length=100,
        default='You May Also Like'
    )
    
    related_products_count = models.IntegerField(
        default=4,
        validators=[MinValueValidator(2), MaxValueValidator(12)]
    )
    
    related_products_algorithm = models.CharField(
        max_length=20,
        choices=[
            ('category', 'Same Category'),
            ('tags', 'Similar Tags'),
            ('manual', 'Manually Selected'),
            ('ai', 'AI Recommendations'),
            ('bestsellers', 'Best Sellers'),
        ],
        default='category'
    )
    
    # === RECENTLY VIEWED ===
    show_recently_viewed = models.BooleanField(
        default=True,
        help_text="Show recently viewed products"
    )
    
    recently_viewed_title = models.CharField(
        max_length=100,
        default='Recently Viewed'
    )
    
    recently_viewed_count = models.IntegerField(
        default=4,
        validators=[MinValueValidator(2), MaxValueValidator(12)]
    )
    
    # === BREADCRUMBS ===
    show_breadcrumbs = models.BooleanField(default=True)
    
    breadcrumb_style = models.CharField(
        max_length=20,
        choices=[
            ('arrows', 'Arrows (Home > Category > Product)'),
            ('slashes', 'Slashes (Home / Category / Product)'),
            ('dots', 'Dots (Home · Category · Product)'),
        ],
        default='arrows'
    )
    
    # === WISHLIST & COMPARE ===
    show_wishlist_button = models.BooleanField(
        default=True,
        help_text="Show 'Add to Wishlist' button"
    )
    
    show_compare_button = models.BooleanField(
        default=False,
        help_text="Show 'Add to Compare' button"
    )
    
    # === DELIVERY INFO ===
    show_estimated_delivery = models.BooleanField(
        default=True,
        help_text="Show estimated delivery date"
    )
    
    show_shipping_calculator = models.BooleanField(
        default=False,
        help_text="Show shipping cost calculator"
    )
    
    show_store_pickup_option = models.BooleanField(
        default=False,
        help_text="Show 'Available for pickup' option"
    )
    
    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'product_page_settings'
        verbose_name = 'Product Page Setting'
        verbose_name_plural = 'Product Page Settings'
    
    def __str__(self):
        return "Product Page Settings"
    
    def clean(self):
        errors = {}
        
        if self.min_quantity > self.max_quantity:
            errors['min_quantity'] = "Minimum quantity cannot exceed maximum quantity."
        
        if self.quantity_increments > self.max_quantity:
            errors['quantity_increments'] = "Quantity increment cannot exceed maximum quantity."
        
        if errors:
            raise ValidationError(errors)



