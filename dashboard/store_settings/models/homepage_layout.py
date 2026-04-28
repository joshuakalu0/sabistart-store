from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class HomepageLayout(models.Model):
    """
    Define homepage structure and section order.

    CONTROLS:
    - Which sections to show
    - Section order
    - Section-specific settings

    AVAILABLE SECTIONS:
    - Hero/Banner Slider
    - Featured Categories
    - Featured Products
    - New Arrivals
    - Best Sellers
    - Sale Items
    - Custom HTML blocks
    - Instagram Feed
    - Testimonials
    - Blog Posts

    IMPACT:
    - Homepage appearance and flow
    - First impression for visitors

    SHOPIFY EQUIVALENT: Theme > Homepage sections
    """

    # === HERO SECTION ===
    show_hero = models.BooleanField(default=True)

    HERO_TYPE_CHOICES = [
        ('slider', 'Image Slider/Carousel'),
        ('video', 'Video Background'),
        ('static', 'Static Image with Text'),
        ('split', 'Split (Image + Text)'),
    ]

    hero_type = models.CharField(
        max_length=20,
        choices=HERO_TYPE_CHOICES,
        default='slider'
    )

    hero_height = models.CharField(
        max_length=20,
        choices=[
            ('small', 'Small (400px)'),
            ('medium', 'Medium (600px)'),
            ('large', 'Large (800px)'),
            ('fullscreen', 'Full Screen'),
        ],
        default='large'
    )

    hero_autoplay = models.BooleanField(
        default=True,
        help_text="Auto-advance slider"
    )

    hero_autoplay_speed = models.IntegerField(
        default=5000,
        validators=[MinValueValidator(2000), MaxValueValidator(10000)],
        help_text="Milliseconds between slides"
    )

    # === FEATURED CATEGORIES ===
    show_featured_categories = models.BooleanField(default=True)

    featured_categories_title = models.CharField(
        max_length=100,
        default='Shop by Category'
    )

    featured_categories_layout = models.CharField(
        max_length=20,
        choices=[
            ('grid', 'Grid Layout'),
            ('carousel', 'Scrolling Carousel'),
            ('cards', 'Card Style'),
        ],
        default='grid'
    )

    featured_categories_count = models.IntegerField(
        default=6,
        validators=[MinValueValidator(3), MaxValueValidator(12)]
    )

    # === FEATURED PRODUCTS ===
    show_featured_products = models.BooleanField(default=True)

    featured_products_title = models.CharField(
        max_length=100,
        default='Featured Products'
    )

    featured_products_count = models.IntegerField(
        default=8,
        validators=[MinValueValidator(4), MaxValueValidator(20)]
    )

    # === NEW ARRIVALS ===
    show_new_arrivals = models.BooleanField(default=True)

    new_arrivals_title = models.CharField(
        max_length=100,
        default='New Arrivals'
    )

    new_arrivals_count = models.IntegerField(
        default=8,
        validators=[MinValueValidator(4), MaxValueValidator(20)]
    )

    new_arrivals_days = models.IntegerField(
        default=30,
        validators=[MinValueValidator(7), MaxValueValidator(90)],
        help_text="Products added in last N days"
    )

    # === BEST SELLERS ===
    show_best_sellers = models.BooleanField(default=True)

    best_sellers_title = models.CharField(
        max_length=100,
        default='Best Sellers'
    )

    best_sellers_count = models.IntegerField(
        default=8,
        validators=[MinValueValidator(4), MaxValueValidator(20)]
    )

    # === SALE SECTION ===
    show_sale_section = models.BooleanField(default=True)

    sale_section_title = models.CharField(
        max_length=100,
        default='On Sale'
    )

    sale_section_count = models.IntegerField(
        default=8,
        validators=[MinValueValidator(4), MaxValueValidator(20)]
    )

    # === PROMOTIONAL BANNERS ===
    show_promo_banners = models.BooleanField(default=True)

    promo_banner_layout = models.CharField(
        max_length=20,
        choices=[
            ('single', 'Single Full-Width Banner'),
            ('double', 'Two Side-by-Side'),
            ('triple', 'Three Columns'),
        ],
        default='double'
    )

    # === TESTIMONIALS ===
    show_testimonials = models.BooleanField(default=False)

    testimonials_title = models.CharField(
        max_length=100,
        default='What Our Customers Say'
    )

    testimonials_count = models.IntegerField(
        default=3,
        validators=[MinValueValidator(2), MaxValueValidator(10)]
    )

    # === BLOG POSTS ===
    show_blog_posts = models.BooleanField(default=False)

    blog_posts_title = models.CharField(
        max_length=100,
        default='Latest from Our Blog'
    )

    blog_posts_count = models.IntegerField(
        default=3,
        validators=[MinValueValidator(2), MaxValueValidator(6)]
    )

    # === INSTAGRAM FEED ===
    show_instagram_feed = models.BooleanField(default=False)

    instagram_title = models.CharField(
        max_length=100,
        default='Follow Us on Instagram'
    )

    instagram_handle = models.CharField(
        max_length=100,
        blank=True,
        help_text="Instagram username (without @)"
    )

    # === BRANDS/PARTNERS ===
    show_brands = models.BooleanField(default=False)

    brands_title = models.CharField(
        max_length=100,
        default='Featured Brands'
    )

    # === SECTION ORDER ===
    section_order = models.JSONField(
        default=list,
        help_text="""Order of sections: ['hero', 'categories', 'featured',
        'new_arrivals', 'best_sellers', 'sale', 'testimonials', 'blog', 'instagram']"""
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'homepage_layout'
        verbose_name = 'Homepage Layout'
        verbose_name_plural = 'Homepage Layouts'

    def __str__(self):
        return "Homepage Layout"

    def get_default_section_order(self):
        """Return default section order"""
        return [
            'hero',
            'categories',
            'featured',
            'new_arrivals',
            'best_sellers',
            'promo_banners',
            'sale',
            'testimonials',
            'blog',
            'instagram'
        ]
