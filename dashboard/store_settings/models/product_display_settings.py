from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class ProductDisplaySettings(models.Model):
    """
    Control how products are displayed throughout the store.

    CONTROLS:
    - Product card style
    - Grid layout
    - Product information shown
    - Quick view settings
    - Hover effects

    IMPACT:
    - Product pages
    - Category pages
    - Search results
    - Homepage product sections

    SHOPIFY EQUIVALENT: Theme > Product grid
    """

    # === PRODUCT CARD STYLE ===
    CARD_STYLE_CHOICES = [
        ('classic', 'Classic (Image, Title, Price)'),
        ('minimal', 'Minimal (Clean, Simple)'),
        ('modern', 'Modern (Large Image, Overlay Text)'),
        ('compact', 'Compact (Small Cards)'),
    ]

    card_style = models.CharField(
        max_length=20,
        choices=CARD_STYLE_CHOICES,
        default='classic'
    )

    # === GRID LAYOUT ===
    products_per_row_desktop = models.IntegerField(
        default=4,
        choices=[(2, '2 Products'), (3, '3 Products'), (4, '4 Products'),
                 (5, '5 Products'), (6, '6 Products')],
        help_text="Number of products per row on desktop"
    )

    products_per_row_tablet = models.IntegerField(
        default=3,
        choices=[(2, '2 Products'), (3, '3 Products'), (4, '4 Products')],
        help_text="Number of products per row on tablet"
    )

    products_per_row_mobile = models.IntegerField(
        default=2,
        choices=[(1, '1 Product'), (2, '2 Products')],
        help_text="Number of products per row on mobile"
    )

    products_per_page = models.IntegerField(
        default=24,
        validators=[MinValueValidator(12), MaxValueValidator(100)],
        help_text="Products to show per page"
    )

    # === PRODUCT INFORMATION ===
    show_product_vendor = models.BooleanField(
        default=True,
        help_text="Show brand/vendor name"
    )

    show_product_sku = models.BooleanField(
        default=False,
        help_text="Show SKU on product card"
    )

    show_product_rating = models.BooleanField(
        default=True,
        help_text="Show star rating on card"
    )

    show_review_count = models.BooleanField(
        default=True,
        help_text="Show number of reviews"
    )

    show_short_description = models.BooleanField(
        default=False,
        help_text="Show product excerpt on card"
    )

    short_description_length = models.IntegerField(
        default=100,
        validators=[MinValueValidator(50), MaxValueValidator(200)],
        help_text="Max characters for short description"
    )

    # === BADGES & LABELS ===
    show_sale_badge = models.BooleanField(
        default=True,
        help_text="Show 'Sale' badge on discounted products"
    )

    show_new_badge = models.BooleanField(
        default=True,
        help_text="Show 'New' badge on recent products"
    )

    new_badge_days = models.IntegerField(
        default=14,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        help_text="Days to show 'New' badge"
    )

    show_stock_status = models.BooleanField(
        default=True,
        help_text="Show 'In Stock' / 'Out of Stock'"
    )

    show_discount_percentage = models.BooleanField(
        default=True,
        help_text="Show '20% OFF' on sale products"
    )

    # === PRICING ===
    PRICE_DISPLAY_CHOICES = [
        ('default', 'Price Only'),
        ('with_tax', 'Price (Incl. Tax)'),
        ('compare', 'Sale Price + Original (crossed out)'),
        ('range', 'Price Range (for variants)'),
    ]

    price_display = models.CharField(
        max_length=20,
        choices=PRICE_DISPLAY_CHOICES,
        default='compare'
    )

    show_tax_label = models.BooleanField(
        default=False,
        help_text="Show 'Incl. VAT' or tax info"
    )

    # === IMAGES ===
    IMAGE_RATIO_CHOICES = [
        ('square', 'Square (1:1)'),
        ('portrait', 'Portrait (3:4)'),
        ('landscape', 'Landscape (4:3)'),
        ('auto', 'Original Ratio'),
    ]

    image_ratio = models.CharField(
        max_length=20,
        choices=IMAGE_RATIO_CHOICES,
        default='square'
    )

    HOVER_EFFECT_CHOICES = [
        ('none', 'No Effect'),
        ('zoom', 'Zoom In'),
        ('fade', 'Fade to Second Image'),
        ('slide', 'Slide to Second Image'),
    ]

    image_hover_effect = models.CharField(
        max_length=20,
        choices=HOVER_EFFECT_CHOICES,
        default='fade'
    )

    show_multiple_images = models.BooleanField(
        default=True,
        help_text="Show additional images on hover"
    )

    # === ACTIONS ===
    show_add_to_cart_button = models.BooleanField(
        default=True,
        help_text="Show 'Add to Cart' on product card"
    )

    add_to_cart_style = models.CharField(
        max_length=20,
        choices=[
            ('always', 'Always Visible'),
            ('hover', 'Show on Hover'),
            ('icon', 'Icon Only'),
        ],
        default='hover'
    )

    show_quick_view = models.BooleanField(
        default=True,
        help_text="Enable quick view modal"
    )

    show_wishlist_button = models.BooleanField(
        default=True,
        help_text="Show wishlist/heart icon"
    )

    show_compare_button = models.BooleanField(
        default=False,
        help_text="Show compare icon"
    )

    # === SORTING & FILTERING ===
    default_sort_order = models.CharField(
        max_length=20,
        choices=[
            ('newest', 'Newest First'),
            ('popular', 'Most Popular'),
            ('price_asc', 'Price: Low to High'),
            ('price_desc', 'Price: High to Low'),
            ('name_asc', 'Name: A-Z'),
            ('name_desc', 'Name: Z-A'),
        ],
        default='newest'
    )

    show_filters_sidebar = models.BooleanField(
        default=True,
        help_text="Show filters sidebar on category pages"
    )

    filters_position = models.CharField(
        max_length=20,
        choices=[
            ('left', 'Left Sidebar'),
            ('right', 'Right Sidebar'),
            ('top', 'Top Bar'),
        ],
        default='left'
    )

    # === PAGINATION ===
    PAGINATION_STYLE_CHOICES = [
        ('numbers', 'Page Numbers'),
        ('load_more', 'Load More Button'),
        ('infinite', 'Infinite Scroll'),
    ]

    pagination_style = models.CharField(
        max_length=20,
        choices=PAGINATION_STYLE_CHOICES,
        default='numbers'
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_display_settings'
        verbose_name = 'Product Display Setting'
        verbose_name_plural = 'Product Display Settings'

    def __str__(self):
        return f"Product Display Settings"


