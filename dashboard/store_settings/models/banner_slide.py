from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


class BannerSlide(models.Model):
    """
    Individual slides for homepage hero slider/banners.

    CONTROLS:
    - Banner image
    - Overlay text and buttons
    - Link destination
    - Display order

    IMPACT:
    - Homepage hero section
    - Promotional campaigns

    SHOPIFY EQUIVALENT: Theme > Homepage > Slideshow
    """

    title = models.CharField(max_length=200)

    subtitle = models.CharField(
        max_length=200,
        blank=True,
        help_text="Supporting text below title"
    )

    description = models.TextField(
        blank=True,
        max_length=300,
        help_text="Additional description text"
    )

    # === IMAGE ===
    image_desktop = models.ImageField(
        upload_to='banners/desktop/',
        help_text="Desktop banner (recommended: 1920x800px)"
    )

    image_mobile = models.ImageField(
        upload_to='banners/mobile/',
        blank=True,
        null=True,
        help_text="Mobile banner (recommended: 800x1000px). Uses desktop if not set."
    )

    # === OVERLAY ===
    text_position = models.CharField(
        max_length=20,
        choices=[
            ('left', 'Left'),
            ('center', 'Center'),
            ('right', 'Right'),
            ('top_left', 'Top Left'),
            ('top_center', 'Top Center'),
            ('top_right', 'Top Right'),
            ('bottom_left', 'Bottom Left'),
            ('bottom_center', 'Bottom Center'),
            ('bottom_right', 'Bottom Right'),
        ],
        default='center'
    )

    text_color = models.CharField(
        max_length=7,
        default='#FFFFFF',
        help_text="Text overlay color"
    )

    overlay_opacity = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Dark overlay opacity (0-100%)"
    )

    # === CALL TO ACTION ===
    cta_text = models.CharField(
        max_length=50,
        default='Shop Now',
        help_text="Button text"
    )

    cta_link = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL or product/category slug"
    )

    cta_style = models.CharField(
        max_length=20,
        choices=[
            ('primary', 'Primary Button'),
            ('secondary', 'Secondary Button'),
            ('outline', 'Outline Button'),
            ('text', 'Text Link'),
        ],
        default='primary'
    )

    show_cta = models.BooleanField(
        default=True,
        help_text="Show call-to-action button"
    )

    # === DISPLAY SETTINGS ===
    is_active = models.BooleanField(default=True)

    display_order = models.IntegerField(
        default=0,
        help_text="Lower numbers appear first"
    )

    start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional: Show only after this date"
    )

    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional: Hide after this date"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'banner_slides'
        verbose_name = 'Banner Slide'
        verbose_name_plural = 'Banner Slides'
        ordering = ['display_order', '-created_at']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['display_order']),
        ]

    def __str__(self):
        return self.title

    def is_currently_active(self):
        """Check if banner should be displayed now"""
        if not self.is_active:
            return False

        now = timezone.now()

        if self.start_date and now < self.start_date:
            return False

        if self.end_date and now > self.end_date:
            return False

        return True

    def clean(self):
        # Validate date range
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })
