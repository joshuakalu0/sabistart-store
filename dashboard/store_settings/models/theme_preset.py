from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class ThemePreset(models.Model):
    """
    Pre-configured theme templates for quick setup.

    CONTROLS:
    - Complete theme configuration
    - Color schemes
    - Layout presets

    PRESET TYPES:
    - Minimal: Clean, simple design
    - Bold: Vibrant colors, large elements
    - Elegant: Sophisticated, refined
    - Playful: Fun, colorful
    - Professional: Corporate, serious
    - Modern: Trendy, contemporary

    IMPACT:
    - Quick theme switching
    - Starting point for customization

    SHOPIFY EQUIVALENT: Theme library
    """

    name = models.CharField(
        max_length=100,
        help_text="Preset name (e.g., 'Minimal Black', 'Bold Coral')"
    )

    description = models.TextField(
        max_length=300,
        help_text="What makes this preset unique"
    )

    preview_image = models.ImageField(
        upload_to='theme_presets/',
        blank=True,
        null=True,
        help_text="Preview screenshot"
    )

    # === THEME DATA ===
    # Store complete theme settings as JSON
    theme_config = models.JSONField(
        default=dict,
        help_text="""Complete theme configuration including colors, fonts,
        spacing, etc. Matches ThemeSettings model fields"""
    )

    # === CATEGORIES ===
    STYLE_CHOICES = [
        ('minimal', 'Minimal'),
        ('bold', 'Bold'),
        ('elegant', 'Elegant'),
        ('playful', 'Playful'),
        ('professional', 'Professional'),
        ('modern', 'Modern'),
        ('vintage', 'Vintage'),
        ('luxury', 'Luxury'),
    ]

    style = models.CharField(
        max_length=20,
        choices=STYLE_CHOICES,
        default='modern'
    )

    # === INDUSTRY ===
    INDUSTRY_CHOICES = [
        ('general', 'General/Multi-purpose'),
        ('fashion', 'Fashion & Apparel'),
        ('electronics', 'Electronics'),
        ('beauty', 'Beauty & Cosmetics'),
        ('home', 'Home & Garden'),
        ('food', 'Food & Beverage'),
        ('sports', 'Sports & Fitness'),
        ('books', 'Books & Media'),
        ('jewelry', 'Jewelry & Accessories'),
        ('kids', 'Kids & Baby'),
    ]

    industry = models.CharField(
        max_length=20,
        choices=INDUSTRY_CHOICES,
        default='general'
    )

    # === METADATA ===
    is_default = models.BooleanField(
        default=False,
        help_text="Default preset for new tenants"
    )

    is_featured = models.BooleanField(
        default=False,
        help_text="Show in featured presets"
    )

    usage_count = models.IntegerField(
        default=0,
        help_text="How many tenants use this preset"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'theme_presets'
        verbose_name = 'Theme Preset'
        verbose_name_plural = 'Theme Presets'
        ordering = ['-is_featured', '-usage_count', 'name']
        indexes = [
            models.Index(fields=['is_default']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['style']),
            models.Index(fields=['industry']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_style_display()})"

    def apply_to_theme(self, theme_settings):
        """Apply this preset to a ThemeSettings instance"""
        for field, value in self.theme_config.items():
            if hasattr(theme_settings, field):
                setattr(theme_settings, field, value)
        theme_settings.save()

        # Increment usage counter
        self.usage_count += 1
        self.save(update_fields=['usage_count'])


