from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class CustomCSS(models.Model):
    """
    Advanced CSS customization for power users.

    CONTROLS:
    - Custom CSS rules
    - CSS variable overrides
    - Responsive breakpoints

    USE CASES:
    - Fine-tune spacing
    - Custom animations
    - Brand-specific tweaks
    - Advanced layouts

    IMPACT:
    - Site-wide styling
    - Requires CSS knowledge

    WARNING: Can break theme if used incorrectly

    SHOPIFY EQUIVALENT: Theme > Edit code > Custom CSS
    """

    name = models.CharField(
        max_length=100,
        help_text="Internal name (e.g., 'Header tweaks', 'Custom buttons')"
    )

    css_code = models.TextField(
        help_text="Custom CSS code (without <style> tags)"
    )

    description = models.TextField(
        blank=True,
        max_length=500,
        help_text="What this CSS does (for documentation)"
    )

    # === TARGETING ===
    APPLY_TO_CHOICES = [
        ('all', 'All Pages'),
        ('homepage', 'Homepage Only'),
        ('product_pages', 'Product Pages Only'),
        ('category_pages', 'Category Pages Only'),
        ('checkout', 'Checkout Pages Only'),
        ('custom', 'Custom Pages'),
    ]

    apply_to = models.CharField(
        max_length=20,
        choices=APPLY_TO_CHOICES,
        default='all'
    )

    custom_pages = models.JSONField(
        default=list,
        blank=True,
        help_text="List of page IDs if apply_to='custom'"
    )

    # === RESPONSIVE ===
    apply_to_mobile = models.BooleanField(
        default=True,
        help_text="Apply CSS on mobile devices"
    )

    apply_to_tablet = models.BooleanField(
        default=True,
        help_text="Apply CSS on tablets"
    )

    apply_to_desktop = models.BooleanField(
        default=True,
        help_text="Apply CSS on desktop"
    )

    # === CONTROL ===
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable this CSS block"
    )

    load_order = models.IntegerField(
        default=0,
        help_text="CSS load priority (higher loads later, can override)"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(
        max_length=100,
        blank=True,
        help_text="User who created this CSS"
    )

    class Meta:
        db_table = 'custom_css'
        verbose_name = 'Custom CSS'
        verbose_name_plural = 'Custom CSS'
        ordering = ['load_order', 'name']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['load_order']),
        ]

    def __str__(self):
        return self.name

    def render_css(self):
        """Generate final CSS with media queries if needed"""
        css = self.css_code

        # Wrap in media queries based on device targeting
        if not (self.apply_to_mobile and self.apply_to_tablet and self.apply_to_desktop):
            media_queries = []

            if self.apply_to_desktop and not (self.apply_to_mobile or self.apply_to_tablet):
                css = f"@media (min-width: 1024px) {{\n{css}\n}}"
            elif self.apply_to_tablet and not (self.apply_to_mobile or self.apply_to_desktop):
                css = f"@media (min-width: 768px) and (max-width: 1023px) {{\n{css}\n}}"
            elif self.apply_to_mobile and not (self.apply_to_tablet or self.apply_to_desktop):
                css = f"@media (max-width: 767px) {{\n{css}\n}}"

        return css
