from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class CustomPage(models.Model):
    """
    Custom static pages for store content.

    CONTROLS:
    - Page title and content
    - SEO settings
    - Template layout

    USE CASES:
    - About Us
    - Contact
    - FAQ
    - Size Guide
    - Shipping Information
    - Terms & Conditions

    IMPACT:
    - Store content pages
    - SEO landing pages

    SHOPIFY EQUIVALENT: Online Store > Pages
    """

    PAGE_KIND_CHOICES = [
        ('generic', 'Generic Page'),
        ('privacy_policy', 'Privacy Policy'),
        ('terms_of_service', 'Terms & Conditions'),
        ('cookie_policy', 'Cookie Policy'),
        ('dmca_policy', 'DMCA Policy'),
        ('accessibility_statement', 'Accessibility Statement'),
        ('modern_slavery_statement', 'Modern Slavery Statement'),
        ('compliance_notice', 'Compliance Notice'),
        ('cookie_preferences', 'Cookie Preferences'),
        ('help_center', 'Help Center'),
        ('delivery_information', 'Delivery Information'),
        ('returns_policy', 'Returns Policy'),
        ('warranty_information', 'Warranty Information'),
    ]

    page_kind = models.CharField(
        max_length=50,
        choices=PAGE_KIND_CHOICES,
        default='generic',
        help_text="Use generic for normal custom pages, or a managed kind for fixed storefront routes.",
    )

    title = models.CharField(max_length=200)

    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="URL-friendly version (auto-generated from title)"
    )

    content = models.TextField(
        help_text="Page content (supports HTML)"
    )

    excerpt = models.TextField(
        max_length=300,
        blank=True,
        help_text="Short description (for listings and SEO)"
    )

    # === LAYOUT ===
    TEMPLATE_CHOICES = [
        ('default', 'Default Template'),
        ('full_width', 'Full Width (no sidebar)'),
        ('narrow', 'Narrow Content'),
        ('contact', 'Contact Page'),
        ('faq', 'FAQ Style'),
    ]

    template = models.CharField(
        max_length=20,
        choices=TEMPLATE_CHOICES,
        default='default'
    )

    show_title = models.BooleanField(
        default=True,
        help_text="Display page title"
    )

    show_breadcrumbs = models.BooleanField(
        default=True,
        help_text="Show breadcrumb navigation"
    )

    # === FEATURED IMAGE ===
    featured_image = models.ImageField(
        upload_to='pages/',
        blank=True,
        null=True,
        help_text="Hero image for page header"
    )

    # === SEO ===
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        help_text="SEO title (defaults to page title)"
    )

    meta_description = models.TextField(
        max_length=160,
        blank=True,
        help_text="SEO description"
    )

    # === PUBLISHING ===
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('hidden', 'Hidden (accessible via direct link)'),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )

    is_enabled = models.BooleanField(
        default=True,
        help_text="Turn this page on or off without deleting its content.",
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'custom_pages'
        verbose_name = 'Custom Page'
        verbose_name_plural = 'Custom Pages'
        ordering = ['title']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['status']),
            models.Index(fields=['page_kind']),
            models.Index(fields=['is_enabled']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if not self.meta_title:
            self.meta_title = self.title
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f'/pages/{self.slug}/'
