from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class NavigationMenu(models.Model):
    """
    Custom navigation menus for different locations.

    CONTROLS:
    - Menu name and location
    - Menu items (managed separately)

    LOCATIONS:
    - Header (main navigation)
    - Footer columns
    - Mobile menu
    - Sidebar

    IMPACT:
    - Site navigation structure
    - Multiple menus per tenant

    SHOPIFY EQUIVALENT: Navigation
    """

    name = models.CharField(
        max_length=100,
        help_text="Internal name (e.g., 'Main Menu', 'Footer Links')"
    )

    LOCATION_CHOICES = [
        ('header', 'Header Navigation'),
        ('footer_1', 'Footer Column 1'),
        ('footer_2', 'Footer Column 2'),
        ('footer_3', 'Footer Column 3'),
        ('footer_4', 'Footer Column 4'),
        ('mobile', 'Mobile Menu'),
        ('sidebar', 'Sidebar'),
        ('custom', 'Custom Location'),
    ]

    location = models.CharField(
        max_length=20,
        choices=LOCATION_CHOICES,
        default='header'
    )

    is_active = models.BooleanField(default=True)

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'navigation_menus'
        verbose_name = 'Navigation Menu'
        verbose_name_plural = 'Navigation Menus'
        indexes = [
            models.Index(fields=['location']),
            models.Index(fields=['is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['location'],
                condition=models.Q(is_active=True),
                name='unique_active_menu_per_location'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_location_display()})"


class NavigationMenuItem(models.Model):
    """
    Individual links within navigation menus.

    CONTROLS:
    - Link text and URL
    - Sub-menu items (nested)
    - Display order
    - Custom styling

    SUPPORTS:
    - Multi-level dropdown menus
    - Category links
    - Custom page links
    - External links

    IMPACT:
    - Navigation structure
    - Menu hierarchy

    SHOPIFY EQUIVALENT: Navigation > Menu items
    """

    menu = models.ForeignKey(
        NavigationMenu,
        on_delete=models.CASCADE,
        related_name='items'
    )

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text="Parent menu item (for sub-menus)"
    )

    label = models.CharField(
        max_length=100,
        help_text="Display text"
    )

    LINK_TYPE_CHOICES = [
        ('url', 'Custom URL'),
        ('category', 'Product Category'),
        ('page', 'Custom Page'),
        ('collection', 'Product Collection'),
        ('home', 'Homepage'),
        ('shop', 'Shop Page'),
        ('contact', 'Contact Page'),
        ('about', 'About Page'),
    ]

    link_type = models.CharField(
        max_length=20,
        choices=LINK_TYPE_CHOICES,
        default='url'
    )

    url = models.CharField(
        max_length=500,
        blank=True,
        help_text="Custom URL or slug"
    )

    # For linking to specific models
    category_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Product category ID (if link_type=category)"
    )

    page_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Custom page ID (if link_type=page)"
    )

    # Display settings
    display_order = models.IntegerField(
        default=0,
        help_text="Lower numbers appear first"
    )

    is_active = models.BooleanField(default=True)

    open_in_new_tab = models.BooleanField(
        default=False,
        help_text="Open link in new window"
    )

    # Optional icon
    icon_class = models.CharField(
        max_length=50,
        blank=True,
        help_text="CSS icon class (e.g., 'fa fa-home')"
    )

    # Mega menu settings
    show_as_mega_menu = models.BooleanField(
        default=False,
        help_text="Display children as mega menu dropdown"
    )

    mega_menu_columns = models.IntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="Number of columns in mega menu"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'navigation_menu_items'
        verbose_name = 'Navigation Menu Item'
        verbose_name_plural = 'Navigation Menu Items'
        ordering = ['display_order', 'label']
        indexes = [
            models.Index(fields=['menu']),
            models.Index(fields=['parent']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.label} ({self.menu.name})"

    def get_url(self):
        """Generate actual URL based on link type"""
        if self.link_type == 'url':
            return self.url
        elif self.link_type == 'home':
            return '/'
        elif self.link_type == 'shop':
            return '/shop/'
        elif self.link_type == 'contact':
            return '/contact/'
        elif self.link_type == 'about':
            return '/about/'
        elif self.link_type == 'category' and self.category_id:
            return f'/category/{self.category_id}/'
        elif self.link_type == 'page' and self.page_id:
            return f'/page/{self.page_id}/'
        return '#'
