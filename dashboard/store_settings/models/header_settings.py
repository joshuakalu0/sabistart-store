from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class HeaderSettings(models.Model):
    """
    Customize header/navigation bar appearance and behavior.

    CONTROLS:
    - Header layout (sticky, transparent, etc.)
    - Logo position and size
    - Navigation style
    - Top announcement bar
    - Search bar visibility
    - Cart icon style

    IMPACT:
    - Affects top navigation on all pages
    - First thing customers see

    SHOPIFY EQUIVALENT: Theme > Header
    """

    # === HEADER LAYOUT ===
    LAYOUT_CHOICES = [
        ('default', 'Default (Logo Left, Nav Center, Icons Right)'),
        ('centered', 'Centered (Logo Center, Nav Below)'),
        ('minimal', 'Minimal (Logo Left, Nav Right)'),
        ('sidebar', 'Sidebar Navigation'),
    ]

    layout = models.CharField(
        max_length=20,
        choices=LAYOUT_CHOICES,
        default='default'
    )

    is_sticky = models.BooleanField(
        default=True,
        help_text="Header stays visible when scrolling"
    )

    is_transparent = models.BooleanField(
        default=False,
        help_text="Transparent header on homepage (overlays hero)"
    )

    background_color = models.CharField(
        max_length=7,
        default='#FFFFFF',
        help_text="Header background color"
    )

    text_color = models.CharField(
        max_length=7,
        default='#000000',
        help_text="Header text/icon color"
    )

    height = models.IntegerField(
        default=80,
        validators=[MinValueValidator(60), MaxValueValidator(150)],
        help_text="Header height in pixels"
    )

    # === LOGO ===
    logo_max_width = models.IntegerField(
        default=180,
        validators=[MinValueValidator(80), MaxValueValidator(400)],
        help_text="Maximum logo width in pixels"
    )

    logo_position = models.CharField(
        max_length=20,
        choices=[
            ('left', 'Left'),
            ('center', 'Center'),
            ('right', 'Right'),
        ],
        default='left'
    )

    # === ANNOUNCEMENT BAR ===
    show_announcement_bar = models.BooleanField(default=False)

    announcement_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g., 'Free shipping on orders over $50!'"
    )

    announcement_background_color = models.CharField(
        max_length=7,
        default='#000000'
    )

    announcement_text_color = models.CharField(
        max_length=7,
        default='#FFFFFF'
    )

    announcement_link = models.URLField(
        blank=True,
        help_text="Optional link when clicking announcement"
    )

    # === NAVIGATION ===
    nav_style = models.CharField(
        max_length=20,
        choices=[
            ('horizontal', 'Horizontal Menu'),
            ('dropdown', 'Dropdown Mega Menu'),
            ('sidebar', 'Sidebar Drawer'),
        ],
        default='horizontal'
    )

    show_categories_in_nav = models.BooleanField(
        default=True,
        help_text="Show product categories in main navigation"
    )

    max_nav_items = models.IntegerField(
        default=7,
        validators=[MinValueValidator(3), MaxValueValidator(12)],
        help_text="Maximum items in main navigation before 'More' dropdown"
    )

    # === SEARCH ===
    show_search = models.BooleanField(default=True)

    search_style = models.CharField(
        max_length=20,
        choices=[
            ('icon', 'Search Icon (opens modal)'),
            ('bar', 'Always Visible Search Bar'),
            ('dropdown', 'Dropdown Search'),
        ],
        default='icon'
    )

    search_placeholder = models.CharField(
        max_length=100,
        default='Search products...'
    )

    # === CART & ACCOUNT ===
    show_cart_icon = models.BooleanField(default=True)

    cart_icon_style = models.CharField(
        max_length=20,
        choices=[
            ('bag', 'Shopping Bag'),
            ('cart', 'Shopping Cart'),
            ('basket', 'Basket'),
        ],
        default='bag'
    )

    show_cart_count = models.BooleanField(
        default=True,
        help_text="Show item count badge on cart icon"
    )

    cart_preview_on_hover = models.BooleanField(
        default=True,
        help_text="Show mini cart preview on hover"
    )

    show_account_icon = models.BooleanField(default=True)
    show_wishlist_icon = models.BooleanField(default=True)

    # === MOBILE MENU ===
    mobile_menu_style = models.CharField(
        max_length=20,
        choices=[
            ('slide', 'Slide from Left'),
            ('slide_right', 'Slide from Right'),
            ('full', 'Full Screen Overlay'),
        ],
        default='slide'
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'header_settings'
        verbose_name = 'Header Setting'
        verbose_name_plural = 'Header Settings'

    def __str__(self):
        return f"Header Settings ({self.layout})"
