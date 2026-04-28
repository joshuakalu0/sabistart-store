"""
Professional Store Settings System - Enterprise Edition
Consolidated, robust settings architecture for multi-tenant e-commerce

Design Philosophy:
- Single source of truth with organized field groups
- Comprehensive validation and business logic
- Performance-optimized with caching and indexing
- Clean API for settings access
- Proper foreign key relationships for data consistency
- Auto-initialization via signals for new tenants
- Full customization coverage for enterprise e-commerce

Architecture:
- Multi-tenant schema isolation (django-tenants)
- Singleton pattern for core settings
- Signal-based auto-initialization
- Cache-optimized for performance
- Comprehensive validation
"""

import uuid
import logging
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, EmailValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.functional import cached_property
from decimal import Decimal
from django.core.cache import cache
from django.db import connection
from django.utils.text import slugify
from django.db.models.signals import post_migrate, post_save, post_delete
from django.dispatch import receiver
import re

logger = logging.getLogger(__name__)


# ============================================================================
# 1. THEME SETTINGS - Visual Identity
# ============================================================================
class ThemeSettings(models.Model):
    """
    Core visual theme for the entire storefront.

    CONTROLS:
    - Brand colors (primary, secondary, accent)
    - Typography (fonts, sizes)
    - Spacing and layout
    - Border radius and shadows
    - Button styles

    IMPACT:
    - Affects entire site appearance
    - One theme per tenant
    - Changes apply site-wide instantly

    SHOPIFY EQUIVALENT: Theme customization > Colors & Typography
    """

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    theme_name = models.CharField(max_length=100, default="Default Theme")

    # === COLOR SCHEME ===
    # Primary brand color (main buttons, links, accents)
    primary_color = models.CharField(
        max_length=7,
        default="#2563EB",
        help_text="Main brand color (hex format: #RRGGBB)"
    )

    # Secondary color (hover states, secondary buttons)
    secondary_color = models.CharField(
        max_length=7,
        default="#1E40AF",
        help_text="Secondary brand color"
    )

    # Accent color (badges, notifications, highlights)
    accent_color = models.CharField(
        max_length=7,
        default="#F59E0B",
        help_text="Accent color for highlights"
    )

    # Background colors
    background_color = models.CharField(
        max_length=7,
        default="#FFFFFF",
        help_text="Main background color"
    )

    secondary_background_color = models.CharField(
        max_length=7,
        default="#F9FAFB",
        help_text="Alternate background (sections, cards)"
    )

    # Text colors
    text_color = models.CharField(
        max_length=7,
        default="#111827",
        help_text="Main text color"
    )

    secondary_text_color = models.CharField(
        max_length=7,
        default="#6B7280",
        help_text="Secondary text (descriptions, meta)"
    )

    # Border and divider colors
    border_color = models.CharField(
        max_length=7,
        default="#E5E7EB",
        help_text="Border and divider color"
    )

    # Success, warning, error colors
    success_color = models.CharField(max_length=7, default="#10B981")
    warning_color = models.CharField(max_length=7, default="#F59E0B")
    error_color = models.CharField(max_length=7, default="#EF4444")

    # === TYPOGRAPHY ===
    # Font families
    FONT_CHOICES = [
        ('system', 'System Default'),
        ('inter', 'Inter'),
        ('roboto', 'Roboto'),
        ('open-sans', 'Open Sans'),
        ('lato', 'Lato'),
        ('montserrat', 'Montserrat'),
        ('poppins', 'Poppins'),
        ('playfair', 'Playfair Display'),
        ('merriweather', 'Merriweather'),
        ('custom', 'Custom Font'),
    ]

    heading_font = models.CharField(
        max_length=50,
        choices=FONT_CHOICES,
        default='inter',
        help_text="Font for headings (H1-H6)"
    )

    body_font = models.CharField(
        max_length=50,
        choices=FONT_CHOICES,
        default='inter',
        help_text="Font for body text"
    )

    custom_font_url = models.URLField(
        blank=True,
        help_text="Google Fonts URL or custom font URL"
    )

    # Font sizes (in rem units)
    base_font_size = models.IntegerField(
        default=16,
        validators=[MinValueValidator(12), MaxValueValidator(20)],
        help_text="Base font size in pixels"
    )

    heading_size_multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=1.5,
        validators=[MinValueValidator(1.0), MaxValueValidator(3.0)],
        help_text="H1 size multiplier (relative to base)"
    )

    # Font weights
    heading_font_weight = models.IntegerField(
        default=700,
        choices=[(300, 'Light'), (400, 'Regular'), (500, 'Medium'),
                 (600, 'Semi-Bold'), (700, 'Bold'), (800, 'Extra Bold')],
        help_text="Font weight for headings"
    )

    body_font_weight = models.IntegerField(
        default=400,
        choices=[(300, 'Light'), (400, 'Regular'), (500, 'Medium'),
                 (600, 'Semi-Bold')],
        help_text="Font weight for body text"
    )

    # === LAYOUT & SPACING ===
    container_width = models.IntegerField(
        default=1200,
        validators=[MinValueValidator(960), MaxValueValidator(1920)],
        help_text="Max content width in pixels"
    )

    SPACING_CHOICES = [
        ('compact', 'Compact'),
        ('normal', 'Normal'),
        ('relaxed', 'Relaxed'),
        ('spacious', 'Spacious'),
    ]

    spacing_scale = models.CharField(
        max_length=20,
        choices=SPACING_CHOICES,
        default='normal',
        help_text="Overall spacing between elements"
    )

    # === BORDERS & SHADOWS ===
    border_radius = models.IntegerField(
        default=8,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Corner radius in pixels (0 = sharp, 50 = very round)"
    )

    use_shadows = models.BooleanField(
        default=True,
        help_text="Enable drop shadows on cards and elements"
    )

    shadow_intensity = models.CharField(
        max_length=20,
        choices=[
            ('none', 'None'),
            ('subtle', 'Subtle'),
            ('medium', 'Medium'),
            ('strong', 'Strong'),
        ],
        default='medium'
    )

    # === BUTTONS ===
    BUTTON_STYLE_CHOICES = [
        ('solid', 'Solid Fill'),
        ('outline', 'Outline'),
        ('ghost', 'Ghost'),
        ('gradient', 'Gradient'),
    ]

    primary_button_style = models.CharField(
        max_length=20,
        choices=BUTTON_STYLE_CHOICES,
        default='solid'
    )

    button_border_radius = models.IntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Button corner radius"
    )

    button_text_transform = models.CharField(
        max_length=20,
        choices=[
            ('none', 'Normal'),
            ('uppercase', 'UPPERCASE'),
            ('lowercase', 'lowercase'),
            ('capitalize', 'Capitalize'),
        ],
        default='none'
    )

    class Meta:
        db_table = 'theme_settings'
        verbose_name = 'Theme Setting'
        verbose_name_plural = 'Theme Settings'
        indexes = [
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"Theme: {self.theme_name}"

    def generate_css_variables(self):
        """Generate CSS custom properties from theme settings"""
        return f"""
        :root {{
            /* Colors */
            --color-primary: {self.primary_color};
            --color-secondary: {self.secondary_color};
            --color-accent: {self.accent_color};
            --color-background: {self.background_color};
            --color-background-secondary: {self.secondary_background_color};
            --color-text: {self.text_color};
            --color-text-secondary: {self.secondary_text_color};
            --color-border: {self.border_color};
            --color-success: {self.success_color};
            --color-warning: {self.warning_color};
            --color-error: {self.error_color};

            /* Typography */
            --font-heading: {self.get_font_family(self.heading_font)};
            --font-body: {self.get_font_family(self.body_font)};
            --font-size-base: {self.base_font_size}px;
            --font-weight-heading: {self.heading_font_weight};
            --font-weight-body: {self.body_font_weight};

            /* Layout */
            --container-width: {self.container_width}px;
            --spacing-unit: {self.get_spacing_unit()}px;
            --border-radius: {self.border_radius}px;
            --button-radius: {self.button_border_radius}px;

            /* Shadows */
            --shadow: {self.get_shadow_value()};
        }}
        """

    def get_font_family(self, font_choice):
        """Convert font choice to CSS font-family value"""
        font_map = {
            'system': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            'inter': '"Inter", sans-serif',
            'roboto': '"Roboto", sans-serif',
            'open-sans': '"Open Sans", sans-serif',
            'lato': '"Lato", sans-serif',
            'montserrat': '"Montserrat", sans-serif',
            'poppins': '"Poppins", sans-serif',
            'playfair': '"Playfair Display", serif',
            'merriweather': '"Merriweather", serif',
        }
        return font_map.get(font_choice, font_map['system'])

    def get_spacing_unit(self):
        """Get base spacing unit based on scale"""
        spacing_map = {
            'compact': 4,
            'normal': 8,
            'relaxed': 12,
            'spacious': 16,
        }
        return spacing_map.get(self.spacing_scale, 8)

    def get_shadow_value(self):
        """Get CSS box-shadow value based on intensity"""
        shadows = {
            'none': 'none',
            'subtle': '0 1px 3px rgba(0, 0, 0, 0.1)',
            'medium': '0 4px 6px rgba(0, 0, 0, 0.1)',
            'strong': '0 10px 15px rgba(0, 0, 0, 0.15)',
        }
        return shadows.get(self.shadow_intensity, shadows['medium'])


# ============================================================================
# 2. STOREFRONT SETTINGS - General Store Configuration
# ============================================================================

class StoreSettingsManager(models.Manager):
    """Custom manager for singleton pattern enforcement."""

    def get_settings(self):
        """Get or create the singleton settings instance."""
        cache_key = f'store_settings_{connection.schema_name}'

        if self.exists():
            return self.first()
        else:
            # Create new instance with required field
            settings = cache.get(cache_key)
            if not settings:
                settings = self.first()
                if settings:
                    cache.set(cache_key, settings, 3600)  # 1 hour
                else:
                    settings = self.create(
                        store_name="My Store",
                        contact_email="contact@example.com"
                    )
            settings.initialize_defaults()
            return settings


class StoreSettings(models.Model):
    """
    Comprehensive store settings model.
    Singleton pattern: one instance per tenant schema.
    """

    # ============================================
    # CORE FIELDS
    # ============================================

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    # ============================================
    # GENERAL SETTINGS
    # ============================================

    # Store Identity
    store_name = models.CharField(
        max_length=255,
        help_text="Public store name",
        db_index=True
    )
    store_tagline = models.CharField(
        max_length=255,
        blank=True,
        help_text="Short description/tagline"
    )
    store_description = models.TextField(
        blank=True,
        help_text="Full store description"
    )

    # Contact Information
    contact_email = models.EmailField(
        help_text="Primary contact email",
        validators=[EmailValidator()]
    )
    support_email = models.EmailField(
        blank=True,
        help_text="Customer support email",
        validators=[EmailValidator()]
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Contact phone number"
    )
    whatsapp_number = models.CharField(max_length=20, blank=True)

    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='US')
    postal_code = models.CharField(max_length=20, blank=True)

    # Geolocation (for map display)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude for map display"
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude for map display"
    )

    # Localization
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar ($)'),
        ('EUR', 'Euro (€)'),
        ('GBP', 'British Pound (£)'),
        ('NGN', 'Nigerian Naira (₦)'),
        ('GHS', 'Ghanaian Cedi (₵)'),
        ('KES', 'Kenyan Shilling (KSh)'),
        ('ZAR', 'South African Rand (R)'),
        ('CAD', 'Canadian Dollar ($)'),
        ('AUD', 'Australian Dollar ($)'),
        ('INR', 'Indian Rupee (₹)'),
    ]

    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD'
    )

    currency_position = models.CharField(
        max_length=10,
        choices=[
            ('before', 'Before ($100)'),
            ('after', 'After (100$)'),
            ('before_space', 'Before with space ($ 100)'),
            ('after_space', 'After with space (100 $)'),
        ],
        default='before'
    )

    TIMEZONE_CHOICES = [
        ('UTC', 'UTC'),
        ('America/New_York', 'Eastern Time'),
        ('America/Chicago', 'Central Time'),
        ('America/Denver', 'Mountain Time'),
        ('America/Los_Angeles', 'Pacific Time'),
        ('Europe/London', 'London'),
        ('Europe/Paris', 'Paris'),
        ('Africa/Lagos', 'Lagos'),
        ('Africa/Nairobi', 'Nairobi'),
        ('Asia/Dubai', 'Dubai'),
        ('Asia/Kolkata', 'India'),
        ('Asia/Shanghai', 'China'),
    ]

    timezone = models.CharField(
        max_length=50,
        choices=TIMEZONE_CHOICES,
        default='UTC'
    )

    # Operational Status
    maintenance_mode = models.BooleanField(
        default=False,
        help_text="Enable maintenance mode"
    )
    maintenance_message = models.TextField(
        blank=True,
        help_text="Message shown during maintenance"
    )

    # Pagination
    pagination_items_per_page = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(10), MaxValueValidator(500)],
        help_text="Number of items per page"
    )

    # App Settings
    apple_store_link = models.URLField(
        blank=True,
        help_text="Apple App Store link"
    )
    play_store_link = models.URLField(
        blank=True,
        help_text="Google Play Store link"
    )

    # ============================================
    # BRANDING & APPEARANCE
    # ============================================

    # Logos and Icons
    logo = models.ImageField(
        upload_to='branding/logos/',
        blank=True,
        help_text="Main store logo"
    )
    logo_dark = models.ImageField(
        upload_to='branding/logos/',
        blank=True,
        help_text="Dark mode logo"
    )
    favicon = models.ImageField(
        upload_to='branding/favicons/',
        blank=True,
        help_text="Favicon (16x16 or 32x32)"
    )
    loading_gif = models.FileField(
        upload_to='website/', blank=True, help_text="Loading animation")

    # ============================================
    # SEO & ANALYTICS
    # ============================================
    # Meta Tags
    meta_title = models.CharField(
        max_length=60,
        blank=True,
        help_text="Default page title (max 60 chars)"
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="Default meta description (max 160 chars)"
    )
    meta_keywords = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated keywords"
    )

    # SEO Settings
    robots_txt = models.TextField(
        blank=True,
        help_text="Custom robots.txt content"
    )
    allow_indexing = models.BooleanField(
        default=True,
        help_text="Allow search engines to index"
    )
    sitemap_enabled = models.BooleanField(
        default=True,
        help_text="Enable XML sitemap"
    )

    # Analytics
    google_analytics_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Google Analytics ID (e.g., G-XXXXXXXXXX)"
    )
    google_tag_manager_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Google Tag Manager ID (e.g., GTM-XXXXXXX)"
    )
    facebook_pixel_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Facebook Pixel ID"
    )

    # ============================================
    # SHIPPING SETTINGS
    # ============================================

    shipping_enabled = models.BooleanField(default=True)

    # Free Shipping
    free_shipping_enabled = models.BooleanField(default=False)
    free_shipping_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Minimum order amount for free shipping"
    )

    # Carrier Integration
    use_live_rates = models.BooleanField(
        default=False,
        help_text="Use carrier API for real-time rates"
    )

    # Fulfillment
    processing_time_days = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(365)],
        help_text="Order processing time in days"
    )
    allow_local_pickup = models.BooleanField(default=False)

    # Restrictions
    ship_to_po_boxes = models.BooleanField(default=True)
    require_signature = models.BooleanField(default=False)

    # ============================================
    # TAX SETTINGS
    # ============================================

    tax_enabled = models.BooleanField(default=True)
    prices_include_tax = models.BooleanField(
        default=False,
        help_text="Display prices with tax included"
    )

    # Calculation
    TAX_CALCULATION_CHOICES = [
        ('manual', 'Manual'),
        ('automatic', 'Automatic'),
    ]
    tax_calculation_method = models.CharField(
        max_length=20,
        choices=TAX_CALCULATION_CHOICES,
        default='manual'
    )

    # Default Rate
    default_tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(
            Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Default tax percentage"
    )

    # Shipping Tax
    charge_tax_on_shipping = models.BooleanField(default=True)

    # Business Info
    tax_id_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="VAT/Tax ID number"
    )
    # Display Options
    show_privacy_policy = models.BooleanField(default=True)
    show_terms_of_service = models.BooleanField(default=True)
    show_refund_policy = models.BooleanField(default=True)
    show_shipping_policy = models.BooleanField(default=True)

    # ============================================
    # CHECKOUT SETTINGS
    # ============================================

    # Guest Checkout
    allow_guest_checkout = models.BooleanField(
        default=True,
        help_text="Allow purchases without account"
    )

    # Cart Settings
    cart_expiry_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Days before cart expires"
    )

    # Validation
    validate_address = models.BooleanField(
        default=False,
        help_text="Use address validation service"
    )

    dashboard_path_prefix = models.CharField(max_length=255, default='admin')

    # ============================================
    # FEATURE TOGGLES
    # ============================================

    # Store Features
    enable_reviews = models.BooleanField(default=True)
    enable_wishlist = models.BooleanField(default=True)
    enable_compare = models.BooleanField(default=True)
    enable_gift_cards = models.BooleanField(default=False)
    enable_subscriptions = models.BooleanField(default=False)

    # Social Features
    enable_social_login = models.BooleanField(default=False)
    enable_social_sharing = models.BooleanField(default=True)

    # Marketing
    enable_popup = models.BooleanField(default=False)
    enable_discount_codes = models.BooleanField(default=True)

    # Integrations
    enable_live_chat = models.BooleanField(default=False)
    live_chat_provider = models.CharField(max_length=50, blank=True)

    # Advanced
    enable_api_access = models.BooleanField(default=False)
    enable_webhooks = models.BooleanField(default=False)

    # ============================================
    # CUSTOM MANAGER
    # ============================================

    objects = StoreSettingsManager()

    class Meta:
        db_table = 'store_settings_consolidated'
        verbose_name = 'Store Settings'
        verbose_name_plural = 'Store Settings'
        indexes = [
            models.Index(fields=['store_name']),
            models.Index(fields=['maintenance_mode']),
        ]

    def __str__(self):
        return f"Settings: {self.store_name}"

    # ============================================
    # VALIDATION
    # ============================================

    def clean(self):
        """Comprehensive validation."""
        errors = {}

        # Validate hex colors
        hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
        color_fields = [
            'primary_color', 'secondary_color', 'accent_color',
            'background_color', 'text_color'
        ]
        for field in color_fields:
            if hasattr(self, field):
                value = getattr(self, field)
                if value and not hex_pattern.match(value):
                    errors[field] = f"Invalid hex color format. Use #RRGGBB format."

        # Validate email fields
        if self.support_email and not self.support_email.strip():
            errors['support_email'] = "Support email cannot be empty if provided."

        # Validate phone number (basic)
        if self.phone:
            phone_clean = re.sub(r'[^\d+]', '', self.phone)
            if len(phone_clean) < 10:
                errors['phone'] = "Phone number must be at least 10 digits."

        # Validate coordinates
        if self.latitude is not None:
            if not (-90 <= self.latitude <= 90):
                errors['latitude'] = "Latitude must be between -90 and 90."
        if self.longitude is not None:
            if not (-180 <= self.longitude <= 180):
                errors['longitude'] = "Longitude must be between -180 and 180."

        # Validate meta field lengths
        if self.meta_title and len(self.meta_title) > 60:
            errors['meta_title'] = "Meta title should not exceed 60 characters for SEO."
        if self.meta_description and len(self.meta_description) > 160:
            errors['meta_description'] = "Meta description should not exceed 160 characters for SEO."

        # Validate shipping threshold
        if self.free_shipping_enabled and self.free_shipping_threshold <= 0:
            errors['free_shipping_threshold'] = "Free shipping threshold must be greater than 0."

        # Validate tax rate
        if self.tax_enabled and self.default_tax_rate < 0:
            errors['default_tax_rate'] = "Tax rate cannot be negative."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    # ============================================
    # HELPER METHODS
    # ============================================

    def initialize_defaults(self):
        """Initialize default values for new instances."""
        if not self.store_name:
            self.store_name = "My Store"
        if not self.contact_email:
            self.contact_email = "contact@example.com"

    @cached_property
    def is_maintenance_mode(self):
        """Check if store is in maintenance mode."""
        return self.maintenance_mode

    @cached_property
    def is_operational(self):
        """Check if store is operational."""
        return not self.maintenance_mode

    @cached_property
    def full_address(self):
        """Get formatted full address."""
        parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.state,
            self.postal_code,
            self.country
        ]
        return ', '.join(filter(None, parts))

    @cached_property
    def has_payment_gateway(self):
        """Check if any payment gateway is enabled."""
        # This would be implemented with actual payment gateway models
        return True

    @cached_property
    def has_shipping_method(self):
        """Check if any shipping method is configured."""
        return (
            self.shipping_enabled and (
                self.free_shipping_enabled or
                self.use_live_rates
            )
        )

    def get_active_payment_methods(self):
        """Get list of active payment methods."""
        # This would be implemented with actual payment gateway models
        return []

    def validate_password(self, password):
        """Validate password against policy."""
        # This would be implemented with actual password policy settings
        errors = []
        return errors


# ============================================================================
# 3. HEADER SETTINGS - Header Layout and Appearance
# ============================================================================
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


# ============================================================================
# 4. FOOTER SETTINGS - Footer Content and Layout
# ============================================================================
class FooterSettings(models.Model):
    """
    Customize footer appearance and content.

    CONTROLS:
    - Footer layout and columns
    - Copyright text
    - Payment method icons
    - Newsletter signup
    - Social media links display

    IMPACT:
    - Bottom of every page
    - Trust signals and legal info

    SHOPIFY EQUIVALENT: Theme > Footer
    """

    # === LAYOUT ===
    LAYOUT_CHOICES = [
        ('4_columns', '4 Columns'),
        ('3_columns', '3 Columns'),
        ('2_columns', '2 Columns'),
        ('minimal', 'Minimal (Single Column)'),
    ]

    layout = models.CharField(
        max_length=20,
        choices=LAYOUT_CHOICES,
        default='4_columns'
    )

    background_color = models.CharField(
        max_length=7,
        default='#1F2937'
    )

    text_color = models.CharField(
        max_length=7,
        default='#FFFFFF'
    )

    # === CONTENT ===
    show_logo = models.BooleanField(
        default=True,
        help_text="Show store logo in footer"
    )

    about_text = models.TextField(
        blank=True,
        max_length=300,
        help_text="Short about text (e.g., 'Quality products since 2020')"
    )

    copyright_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g., '© 2024 YourStore. All rights reserved.'"
    )

    # === NEWSLETTER ===
    show_newsletter = models.BooleanField(
        default=True,
        help_text="Show newsletter signup in footer"
    )

    newsletter_title = models.CharField(
        max_length=100,
        default='Subscribe to our newsletter'
    )

    newsletter_description = models.CharField(
        max_length=200,
        default='Get the latest updates on new products and upcoming sales'
    )

    # === PAYMENT METHODS ===
    show_payment_icons = models.BooleanField(
        default=True,
        help_text="Show accepted payment method icons"
    )

    accepted_payments = models.JSONField(
        default=list,
        blank=True,
        help_text="List of payment methods: ['visa', 'mastercard', 'paypal', etc.]"
    )

    # === SOCIAL MEDIA ===
    show_social_links = models.BooleanField(default=True)

    social_links_style = models.CharField(
        max_length=20,
        choices=[
            ('icons', 'Icon Only'),
            ('text', 'Text Links'),
            ('both', 'Icons with Text'),
        ],
        default='icons'
    )

    # === TRUST BADGES ===
    show_trust_badges = models.BooleanField(
        default=False,
        help_text="Show security/trust badges (SSL, verified, etc.)"
    )

    trust_badge_1 = models.ImageField(
        upload_to='footer/badges/',
        blank=True,
        null=True
    )

    trust_badge_2 = models.ImageField(
        upload_to='footer/badges/',
        blank=True,
        null=True
    )

    trust_badge_3 = models.ImageField(
        upload_to='footer/badges/',
        blank=True,
        null=True
    )

    # === LEGAL LINKS ===
    show_legal_links = models.BooleanField(
        default=True,
        help_text="Show Terms, Privacy Policy, etc."
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'footer_settings'
        verbose_name = 'Footer Setting'
        verbose_name_plural = 'Footer Settings'

    def __str__(self):
        return f"Footer Settings ({self.layout})"


# ============================================================================
# 5. HOMEPAGE LAYOUT - Homepage Structure and Sections
# ============================================================================
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


# ============================================================================
# 6. BANNER SLIDE - Individual Banner/Slider Images
# ============================================================================
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


# ============================================================================
# 7. NAVIGATION MENU - Custom Navigation Menus
# ============================================================================
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


# ============================================================================
# 8. NAVIGATION MENU ITEM - Individual Menu Links
# ============================================================================
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


# ============================================================================
# 9. CUSTOM PAGE - Static Pages (About, FAQ, etc.)
# ============================================================================
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


# ============================================================================
# 10. PRODUCT DISPLAY SETTINGS - Product Listing Preferences
# ============================================================================
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


# ============================================================================
# 11. CHECKOUT SETTINGS - Checkout Flow Customization
# ============================================================================
class CheckoutSettings(models.Model):
    """
    Customize checkout process and flow.

    CONTROLS:
    - Checkout steps
    - Field requirements
    - Payment/shipping options display
    - Order confirmation

    IMPACT:
    - Checkout user experience
    - Conversion rate
    - Order completion

    SHOPIFY EQUIVALENT: Settings > Checkout
    """

    # === CHECKOUT FLOW ===
    CHECKOUT_STYLE_CHOICES = [
        ('single_page', 'Single Page Checkout'),
        ('multi_step', 'Multi-Step Checkout'),
        ('accordion', 'Accordion Style'),
    ]

    checkout_style = models.CharField(
        max_length=20,
        choices=CHECKOUT_STYLE_CHOICES,
        default='multi_step'
    )

    show_breadcrumbs = models.BooleanField(
        default=True,
        help_text="Show checkout progress steps"
    )

    show_order_summary = models.BooleanField(
        default=True,
        help_text="Show order summary sidebar"
    )

    order_summary_collapsible = models.BooleanField(
        default=True,
        help_text="Allow collapsing order summary on mobile"
    )

    # === CUSTOMER INFORMATION ===
    require_account_creation = models.BooleanField(
        default=False,
        help_text="Force customers to create account"
    )

    allow_guest_checkout = models.BooleanField(
        default=True,
        help_text="Allow checkout without account"
    )

    show_newsletter_signup = models.BooleanField(
        default=True,
        help_text="Show newsletter checkbox at checkout"
    )

    newsletter_opt_in_default = models.BooleanField(
        default=False,
        help_text="Newsletter checkbox checked by default"
    )

    # === ADDRESS FIELDS ===
    require_phone_number = models.BooleanField(default=True)
    require_company_name = models.BooleanField(default=False)
    require_address_line2 = models.BooleanField(default=False)

    show_delivery_instructions = models.BooleanField(
        default=True,
        help_text="Allow delivery notes/instructions"
    )

    # === SHIPPING ===
    show_shipping_calculator = models.BooleanField(
        default=True,
        help_text="Show shipping cost calculator in cart"
    )

    group_shipping_methods = models.BooleanField(
        default=True,
        help_text="Group by carrier/speed"
    )

    # === PAYMENT ===
    show_payment_icons = models.BooleanField(
        default=True,
        help_text="Show accepted payment method icons"
    )

    show_trust_badges = models.BooleanField(
        default=True,
        help_text="Show security/SSL badges"
    )

    # === CART ===
    enable_cart_notes = models.BooleanField(
        default=True,
        help_text="Allow order notes in cart"
    )

    enable_coupon_codes = models.BooleanField(
        default=True,
        help_text="Allow discount codes"
    )

    show_estimated_total = models.BooleanField(
        default=True,
        help_text="Show estimated total before checkout"
    )

    # === CONFIRMATION PAGE ===
    show_related_products = models.BooleanField(
        default=True,
        help_text="Show product recommendations on thank you page"
    )

    show_social_sharing = models.BooleanField(
        default=False,
        help_text="Allow sharing purchase on social media"
    )

    thank_you_message = models.TextField(
        blank=True,
        max_length=500,
        help_text="Custom message on order confirmation"
    )

    # === LEGAL ===
    show_terms_checkbox = models.BooleanField(
        default=True,
        help_text="Require accepting terms & conditions"
    )

    terms_checkbox_text = models.CharField(
        max_length=200,
        default="I agree to the Terms & Conditions"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'checkout_settings'
        verbose_name = 'Checkout Setting'
        verbose_name_plural = 'Checkout Settings'

    def __str__(self):
        return "Checkout Settings"


# ============================================================================
# 12. EMAIL TEMPLATE SETTINGS - Email Branding
# ============================================================================
class EmailTemplateSettings(models.Model):
    """
    Customize transactional email appearance.

    CONTROLS:
    - Email header/footer
    - Colors and branding
    - Social links in emails

    EMAIL TYPES:
    - Order confirmation
    - Shipping notification
    - Password reset
    - Welcome email
    - Abandoned cart

    IMPACT:
    - Customer communication
    - Brand consistency

    SHOPIFY EQUIVALENT: Settings > Notifications > Email templates
    """

    # === BRANDING ===
    logo = models.ImageField(
        upload_to='emails/logos/',
        blank=True,
        null=True,
        help_text="Logo for email header (recommended: 200x60px)"
    )

    accent_color = models.CharField(
        max_length=7,
        default='#2563EB',
        help_text="Button and link color"
    )

    background_color = models.CharField(
        max_length=7,
        default='#F3F4F6',
        help_text="Email background color"
    )

    content_background_color = models.CharField(
        max_length=7,
        default='#FFFFFF',
        help_text="Content area background"
    )

    text_color = models.CharField(
        max_length=7,
        default='#1F2937'
    )

    # === HEADER ===
    header_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Text above logo (optional)"
    )

    show_social_links_in_header = models.BooleanField(default=False)

    # === FOOTER ===
    footer_text = models.TextField(
        blank=True,
        max_length=500,
        help_text="Footer message (supports HTML)"
    )

    show_contact_info = models.BooleanField(
        default=True,
        help_text="Show store contact info in footer"
    )

    show_social_links_in_footer = models.BooleanField(default=True)

    show_unsubscribe_link = models.BooleanField(
        default=True,
        help_text="Show unsubscribe link (required for marketing emails)"
    )

    # === CONTENT ===
    BUTTON_STYLE_CHOICES = [
        ('solid', 'Solid Button'),
        ('outline', 'Outline Button'),
        ('link', 'Text Link'),
    ]

    button_style = models.CharField(
        max_length=20,
        choices=BUTTON_STYLE_CHOICES,
        default='solid'
    )

    button_border_radius = models.IntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(50)]
    )

    # === TYPOGRAPHY ===
    FONT_CHOICES = [
        ('system', 'System Default'),
        ('arial', 'Arial'),
        ('helvetica', 'Helvetica'),
        ('georgia', 'Georgia'),
        ('times', 'Times New Roman'),
    ]

    font_family = models.CharField(
        max_length=20,
        choices=FONT_CHOICES,
        default='system'
    )

    # === SPECIFIC EMAIL SETTINGS ===
    order_confirmation_custom_message = models.TextField(
        blank=True,
        max_length=300,
        help_text="Additional message in order confirmation emails"
    )

    shipping_notification_custom_message = models.TextField(
        blank=True,
        max_length=300,
        help_text="Additional message in shipping notification emails"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'email_template_settings'
        verbose_name = 'Email Template Setting'
        verbose_name_plural = 'Email Template Settings'

    def __str__(self):
        return "Email Template Settings"

    def get_font_stack(self):
        """Get CSS font stack based on choice"""
        font_stacks = {
            'system': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            'arial': 'Arial, sans-serif',
            'helvetica': 'Helvetica, Arial, sans-serif',
            'georgia': 'Georgia, serif',
            'times': '"Times New Roman", Times, serif',
        }
        return font_stacks.get(self.font_family, font_stacks['system'])


# ============================================================================
# 13. SOCIAL MEDIA LINKS - Social Media Integration
# ============================================================================
class SocialMediaLinks(models.Model):
    """
    Store social media profile links.

    CONTROLS:
    - Social platform URLs
    - Display preferences

    PLATFORMS:
    - Facebook, Instagram, Twitter/X
    - Pinterest, TikTok, YouTube
    - LinkedIn, WhatsApp

    IMPACT:
    - Footer social icons
    - Product sharing
    - Social proof

    SHOPIFY EQUIVALENT: Theme settings > Social media
    """

    # === SOCIAL LINKS ===
    facebook_url = models.URLField(
        blank=True,
        help_text="Full URL (e.g., https://facebook.com/yourstore)"
    )

    instagram_url = models.URLField(blank=True)

    twitter_url = models.URLField(
        blank=True,
        help_text="Twitter/X profile URL"
    )

    pinterest_url = models.URLField(blank=True)

    tiktok_url = models.URLField(blank=True)

    youtube_url = models.URLField(blank=True)

    linkedin_url = models.URLField(blank=True)

    snapchat_url = models.URLField(blank=True)

    whatsapp_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="WhatsApp number with country code (e.g., +1234567890)"
    )

    # === DISPLAY SETTINGS ===
    icon_style = models.CharField(
        max_length=20,
        choices=[
            ('filled', 'Filled Icons'),
            ('outline', 'Outline Icons'),
            ('colored', 'Brand Colors'),
            ('mono', 'Monochrome'),
        ],
        default='filled'
    )

    icon_size = models.CharField(
        max_length=20,
        choices=[
            ('small', 'Small'),
            ('medium', 'Medium'),
            ('large', 'Large'),
        ],
        default='medium'
    )

    # === SHARING ===
    enable_product_sharing = models.BooleanField(
        default=True,
        help_text="Show share buttons on product pages"
    )

    sharing_platforms = models.JSONField(
        default=list,
        blank=True,
        help_text="Platforms for sharing: ['facebook', 'twitter', 'pinterest', 'whatsapp']"
    )

    # === INSTAGRAM INTEGRATION ===
    instagram_access_token = models.CharField(
        max_length=500,
        blank=True,
        help_text="Instagram API token for feed display"
    )

    show_instagram_feed = models.BooleanField(
        default=False,
        help_text="Display Instagram feed on site"
    )

    instagram_feed_count = models.IntegerField(
        default=6,
        validators=[MinValueValidator(4), MaxValueValidator(12)],
        help_text="Number of Instagram photos to show"
    )

    # === FACEBOOK INTEGRATION ===
    facebook_app_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="For Facebook sharing and analytics"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'social_media_links'
        verbose_name = 'Social Media Links'
        verbose_name_plural = 'Social Media Links'

    def __str__(self):
        return "Social Media Links"

    def get_active_platforms(self):
        """Return list of platforms with configured URLs"""
        platforms = []
        if self.facebook_url:
            platforms.append(('facebook', self.facebook_url))
        if self.instagram_url:
            platforms.append(('instagram', self.instagram_url))
        if self.twitter_url:
            platforms.append(('twitter', self.twitter_url))
        if self.pinterest_url:
            platforms.append(('pinterest', self.pinterest_url))
        if self.tiktok_url:
            platforms.append(('tiktok', self.tiktok_url))
        if self.youtube_url:
            platforms.append(('youtube', self.youtube_url))
        if self.linkedin_url:
            platforms.append(('linkedin', self.linkedin_url))
        return platforms


# ============================================================================
# 14. CUSTOM CSS - Advanced Styling Overrides
# ============================================================================
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


# ============================================================================
# 15. THEME PRESET - Pre-built Theme Templates
# ============================================================================
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


# ============================================================================
# 16. PRODUCT PAGE SETTINGS - Individual Product Page Customization
# ============================================================================
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



# ============================================================================
# 17. CART SETTINGS - Shopping Cart Behavior and Appearance
# ============================================================================
class CartSettings(models.Model):
    """
    Shopping cart behavior and appearance customization.

    CONTROLS:
    - Cart type (page, drawer, popup)
    - Cart behavior and interactions
    - Upsells and cross-sells
    - Discount code handling
    - Progress indicators

    IMPACT:
    - Shopping cart user experience
    - Cart abandonment rate
    - Average order value

    SHOPIFY EQUIVALENT: Theme > Cart
    """

    # === CART TYPE ===
    CART_TYPE_CHOICES = [
        ('page', 'Dedicated Cart Page'),
        ('drawer', 'Slide-out Drawer'),
        ('popup', 'Popup Modal'),
        ('dropdown', 'Dropdown from Header'),
        ('mini', 'Mini Cart Preview'),
    ]
    cart_type = models.CharField(
        max_length=20,
        choices=CART_TYPE_CHOICES,
        default='drawer',
        help_text="Cart display style"
    )

    # === DRAWER SETTINGS ===
    drawer_position = models.CharField(
        max_length=10,
        choices=[('left', 'Left'), ('right', 'Right')],
        default='right',
        help_text="Drawer slide-in position"
    )

    drawer_width = models.IntegerField(
        default=400,
        validators=[MinValueValidator(300), MaxValueValidator(600)],
        help_text="Drawer width in pixels"
    )

    drawer_overlay_opacity = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Background overlay opacity (0-100%)"
    )

    # === CART BEHAVIOR ===
    auto_open_on_add = models.BooleanField(
        default=True,
        help_text="Automatically open cart when item added"
    )

    auto_close_delay = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(30)],
        help_text="Auto-close cart after N seconds (0 = never)"
    )

    show_continue_shopping = models.BooleanField(
        default=True,
        help_text="Show 'Continue Shopping' button"
    )

    enable_cart_notes = models.BooleanField(
        default=True,
        help_text="Allow order notes/special instructions"
    )

    enable_gift_message = models.BooleanField(
        default=False,
        help_text="Allow gift message input"
    )

    enable_gift_wrapping = models.BooleanField(
        default=False,
        help_text="Offer gift wrapping option"
    )

    gift_wrapping_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Gift wrapping fee"
    )

    # === CART ITEMS ===
    show_product_images = models.BooleanField(
        default=True,
        help_text="Show product thumbnails"
    )

    image_size = models.CharField(
        max_length=20,
        choices=[
            ('small', 'Small (60px)'),
            ('medium', 'Medium (80px)'),
            ('large', 'Large (100px)'),
        ],
        default='medium'
    )

    show_variant_details = models.BooleanField(
        default=True,
        help_text="Show variant information (size, color, etc.)"
    )

    show_remove_button = models.BooleanField(
        default=True,
        help_text="Show remove/delete item button"
    )

    enable_quantity_update = models.BooleanField(
        default=True,
        help_text="Allow quantity changes in cart"
    )

    show_unit_price = models.BooleanField(
        default=True,
        help_text="Show individual item price"
    )

    show_line_total = models.BooleanField(
        default=True,
        help_text="Show line item total (price × quantity)"
    )

    # === PRICING DISPLAY ===
    show_item_subtotal = models.BooleanField(
        default=True,
        help_text="Show items subtotal"
    )

    show_savings = models.BooleanField(
        default=True,
        help_text="Show total savings/discounts"
    )

    show_tax_estimate = models.BooleanField(
        default=True,
        help_text="Show estimated tax"
    )

    show_shipping_estimate = models.BooleanField(
        default=True,
        help_text="Show estimated shipping cost"
    )

    show_grand_total = models.BooleanField(
        default=True,
        help_text="Show final total"
    )

    # === UPSELLS & CROSS-SELLS ===
    enable_cart_upsells = models.BooleanField(
        default=False,
        help_text="Show product recommendations in cart"
    )

    upsell_title = models.CharField(
        max_length=100,
        default='Frequently Bought Together'
    )

    upsell_count = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="Number of upsell products to show"
    )

    upsell_algorithm = models.CharField(
        max_length=20,
        choices=[
            ('related', 'Related Products'),
            ('frequently_bought', 'Frequently Bought Together'),
            ('bestsellers', 'Best Sellers'),
            ('manual', 'Manual Selection'),
        ],
        default='frequently_bought'
    )

    # === FREE SHIPPING PROGRESS ===
    show_free_shipping_progress = models.BooleanField(
        default=True,
        help_text="Show progress bar for free shipping threshold"
    )

    free_shipping_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('50.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Free shipping minimum order amount"
    )

    progress_bar_color = models.CharField(
        max_length=7,
        default='#10B981',
        help_text="Progress bar color (hex)"
    )

    progress_message_below = models.CharField(
        max_length=200,
        default='Add {amount} more to get FREE shipping!',
        help_text="Message when below threshold (use {amount} placeholder)"
    )

    progress_message_reached = models.CharField(
        max_length=200,
        default='You qualify for FREE shipping!',
        help_text="Message when threshold reached"
    )

    # === DISCOUNT CODES ===
    show_discount_code_field = models.BooleanField(
        default=True,
        help_text="Show discount/promo code input"
    )

    discount_code_placeholder = models.CharField(
        max_length=50,
        default='Enter discount code'
    )

    discount_code_position = models.CharField(
        max_length=20,
        choices=[
            ('top', 'Top of Cart'),
            ('bottom', 'Bottom of Cart'),
            ('collapsed', 'Collapsed/Hidden by Default'),
        ],
        default='bottom'
    )

    # === CHECKOUT BUTTON ===
    checkout_button_text = models.CharField(
        max_length=50,
        default='Proceed to Checkout'
    )

    checkout_button_style = models.CharField(
        max_length=20,
        choices=[
            ('primary', 'Primary Button'),
            ('large', 'Large Prominent Button'),
            ('full_width', 'Full Width Button'),
        ],
        default='full_width'
    )

    show_secure_checkout_badge = models.BooleanField(
        default=True,
        help_text="Show 'Secure Checkout' badge/icon"
    )

    show_accepted_payments = models.BooleanField(
        default=True,
        help_text="Show accepted payment method icons"
    )

    show_money_back_guarantee = models.BooleanField(
        default=False,
        help_text="Show money-back guarantee badge"
    )

    # === EMPTY CART ===
    empty_cart_message = models.CharField(
        max_length=200,
        default='Your cart is empty'
    )

    empty_cart_icon = models.CharField(
        max_length=50,
        default='shopping-cart',
        help_text="Icon to show for empty cart"
    )

    show_continue_shopping_on_empty = models.BooleanField(
        default=True,
        help_text="Show 'Continue Shopping' button when cart empty"
    )

    show_popular_products_on_empty = models.BooleanField(
        default=True,
        help_text="Show popular products when cart is empty"
    )

    popular_products_count = models.IntegerField(
        default=4,
        validators=[MinValueValidator(2), MaxValueValidator(12)]
    )

    # === CART EXPIRY ===
    enable_cart_expiry = models.BooleanField(
        default=True,
        help_text="Automatically clear old cart items"
    )

    cart_expiry_days = models.IntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Days before cart items expire"
    )

    show_expiry_warning = models.BooleanField(
        default=True,
        help_text="Warn users about expiring cart items"
    )

    # === STOCK WARNINGS ===
    show_low_stock_warning = models.BooleanField(
        default=True,
        help_text="Show warning for low stock items in cart"
    )

    show_out_of_stock_warning = models.BooleanField(
        default=True,
        help_text="Show warning for out of stock items"
    )

    auto_remove_out_of_stock = models.BooleanField(
        default=False,
        help_text="Automatically remove out of stock items"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cart_settings'
        verbose_name = 'Cart Setting'
        verbose_name_plural = 'Cart Settings'

    def __str__(self):
        return "Cart Settings"

    def clean(self):
        errors = {}

        if self.free_shipping_threshold < 0:
            errors['free_shipping_threshold'] = "Free shipping threshold cannot be negative."

        if self.gift_wrapping_price < 0:
            errors['gift_wrapping_price'] = "Gift wrapping price cannot be negative."

        if errors:
            raise ValidationError(errors)


# ============================================================================
# 18. SEARCH SETTINGS - Search Functionality Configuration
# ============================================================================
class SearchSettings(models.Model):
    """
    Search functionality and results display configuration.

    CONTROLS:
    - Search behavior and autocomplete
    - Search scope (products, pages, blog)
    - Results display and filtering
    - Search suggestions

    IMPACT:
    - Product discoverability
    - User experience
    - Conversion rate

    SHOPIFY EQUIVALENT: Theme > Search
    """

    # === SEARCH BEHAVIOR ===
    enable_autocomplete = models.BooleanField(
        default=True,
        help_text="Show search suggestions as user types"
    )

    autocomplete_delay = models.IntegerField(
        default=300,
        validators=[MinValueValidator(100), MaxValueValidator(2000)],
        help_text="Delay before showing suggestions (milliseconds)"
    )

    min_characters = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Minimum characters before triggering search"
    )

    max_suggestions = models.IntegerField(
        default=8,
        validators=[MinValueValidator(3), MaxValueValidator(20)],
        help_text="Maximum number of autocomplete suggestions"
    )

    # === SEARCH SCOPE ===
    search_products = models.BooleanField(
        default=True,
        help_text="Include products in search"
    )

    search_product_title = models.BooleanField(
        default=True,
        help_text="Search in product titles"
    )

    search_product_description = models.BooleanField(
        default=True,
        help_text="Search in product descriptions"
    )

    search_product_sku = models.BooleanField(
        default=True,
        help_text="Search by product SKU"
    )

    search_product_tags = models.BooleanField(
        default=True,
        help_text="Search in product tags"
    )

    search_categories = models.BooleanField(
        default=True,
        help_text="Include categories in search"
    )

    search_pages = models.BooleanField(
        default=True,
        help_text="Include custom pages in search"
    )

    search_blog_posts = models.BooleanField(
        default=False,
        help_text="Include blog posts in search"
    )

    search_vendors = models.BooleanField(
        default=False,
        help_text="Search by vendor/brand name"
    )

    # === AUTOCOMPLETE DISPLAY ===
    show_product_images = models.BooleanField(
        default=True,
        help_text="Show product images in autocomplete"
    )

    show_product_prices = models.BooleanField(
        default=True,
        help_text="Show prices in autocomplete"
    )

    show_product_ratings = models.BooleanField(
        default=False,
        help_text="Show ratings in autocomplete"
    )

    show_stock_status = models.BooleanField(
        default=True,
        help_text="Show stock status in autocomplete"
    )

    show_category_suggestions = models.BooleanField(
        default=True,
        help_text="Show matching categories"
    )

    show_popular_searches = models.BooleanField(
        default=True,
        help_text="Show popular/trending searches"
    )

    popular_searches_count = models.IntegerField(
        default=5,
        validators=[MinValueValidator(3), MaxValueValidator(10)]
    )

    # === SEARCH RESULTS PAGE ===
    results_per_page = models.IntegerField(
        default=24,
        validators=[MinValueValidator(12), MaxValueValidator(100)],
        help_text="Products per page in search results"
    )

    results_layout = models.CharField(
        max_length=20,
        choices=[
            ('grid', 'Grid Layout'),
            ('list', 'List Layout'),
            ('mixed', 'Mixed Layout'),
        ],
        default='grid'
    )

    show_filters = models.BooleanField(
        default=True,
        help_text="Show filter sidebar on results page"
    )

    show_sort_options = models.BooleanField(
        default=True,
        help_text="Show sort dropdown"
    )

    show_search_term = models.BooleanField(
        default=True,
        help_text="Display search query at top of results"
    )

    show_result_count = models.BooleanField(
        default=True,
        help_text="Show number of results found"
    )

    show_search_time = models.BooleanField(
        default=False,
        help_text="Show search execution time"
    )

    # === SEARCH ALGORITHM ===
    enable_fuzzy_search = models.BooleanField(
        default=True,
        help_text="Tolerate typos and misspellings"
    )

    fuzzy_threshold = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Maximum character differences for fuzzy matching"
    )

    enable_synonym_search = models.BooleanField(
        default=False,
        help_text="Search for synonyms (e.g., 'phone' finds 'mobile')"
    )

    enable_partial_match = models.BooleanField(
        default=True,
        help_text="Match partial words (e.g., 'run' finds 'running')"
    )

    search_ranking = models.CharField(
        max_length=20,
        choices=[
            ('relevance', 'Relevance'),
            ('popularity', 'Popularity'),
            ('newest', 'Newest First'),
            ('price_asc', 'Price: Low to High'),
            ('price_desc', 'Price: High to Low'),
        ],
        default='relevance',
        help_text="Default search result ranking"
    )

    # === NO RESULTS ===
    no_results_message = models.CharField(
        max_length=200,
        default='No products found for "{query}"',
        help_text="Message when no results (use {query} placeholder)"
    )

    show_suggestions_on_no_results = models.BooleanField(
        default=True,
        help_text="Show 'Did you mean...' suggestions"
    )

    show_popular_products_on_no_results = models.BooleanField(
        default=True,
        help_text="Show popular products when no results"
    )

    popular_products_title = models.CharField(
        max_length=100,
        default='Popular Products'
    )

    popular_products_count = models.IntegerField(
        default=8,
        validators=[MinValueValidator(4), MaxValueValidator(20)]
    )

    show_all_categories_on_no_results = models.BooleanField(
        default=False,
        help_text="Show category list when no results"
    )

    # === SEARCH ANALYTICS ===
    track_search_queries = models.BooleanField(
        default=True,
        help_text="Track search queries for analytics"
    )

    track_no_results_queries = models.BooleanField(
        default=True,
        help_text="Track queries that returned no results"
    )

    track_click_through = models.BooleanField(
        default=True,
        help_text="Track which results users click"
    )

    # === ADVANCED ===
    enable_voice_search = models.BooleanField(
        default=False,
        help_text="Enable voice search input"
    )

    enable_barcode_search = models.BooleanField(
        default=False,
        help_text="Enable barcode/QR code search"
    )

    enable_image_search = models.BooleanField(
        default=False,
        help_text="Enable visual/image search"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'search_settings'
        verbose_name = 'Search Setting'
        verbose_name_plural = 'Search Settings'

    def __str__(self):
        return "Search Settings"

    def clean(self):
        errors = {}

        if not any([self.search_products, self.search_categories,
                   self.search_pages, self.search_blog_posts]):
            errors['search_products'] = "At least one search scope must be enabled."

        if errors:
            raise ValidationError(errors)



# ============================================================================
# 19. NOTIFICATION SETTINGS - Email and SMS Notifications
# ============================================================================
class NotificationSettings(models.Model):
    """
    Email and SMS notification configuration.

    CONTROLS:
    - Email notification triggers
    - SMS notification settings
    - Admin notifications
    - Customer notifications
    - Marketing communications

    IMPACT:
    - Customer communication
    - Order updates
    - Marketing campaigns

    SHOPIFY EQUIVALENT: Settings > Notifications
    """

    # === EMAIL NOTIFICATIONS - ORDERS ===
    send_order_confirmation = models.BooleanField(
        default=True,
        help_text="Send order confirmation email"
    )

    send_order_processing = models.BooleanField(
        default=True,
        help_text="Send email when order is being processed"
    )

    send_order_shipped = models.BooleanField(
        default=True,
        help_text="Send shipping notification"
    )

    send_order_delivered = models.BooleanField(
        default=True,
        help_text="Send delivery confirmation"
    )

    send_order_cancelled = models.BooleanField(
        default=True,
        help_text="Send cancellation notification"
    )

    send_order_refunded = models.BooleanField(
        default=True,
        help_text="Send refund notification"
    )

    send_order_on_hold = models.BooleanField(
        default=True,
        help_text="Send notification when order on hold"
    )

    # === EMAIL NOTIFICATIONS - CUSTOMER ===
    send_welcome_email = models.BooleanField(
        default=True,
        help_text="Send welcome email to new customers"
    )

    send_password_reset = models.BooleanField(
        default=True,
        help_text="Send password reset emails"
    )

    send_account_verification = models.BooleanField(
        default=True,
        help_text="Send email verification link"
    )

    send_wishlist_reminder = models.BooleanField(
        default=False,
        help_text="Send wishlist reminder emails"
    )

    wishlist_reminder_days = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        help_text="Days before sending wishlist reminder"
    )

    # === EMAIL NOTIFICATIONS - MARKETING ===
    send_abandoned_cart = models.BooleanField(
        default=True,
        help_text="Send abandoned cart recovery emails"
    )

    abandoned_cart_delay_hours = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(72)],
        help_text="Hours before sending first abandoned cart email"
    )

    abandoned_cart_series_count = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Number of abandoned cart emails to send"
    )

    send_back_in_stock = models.BooleanField(
        default=True,
        help_text="Notify customers when out-of-stock items return"
    )

    send_price_drop_alert = models.BooleanField(
        default=False,
        help_text="Notify customers of price drops on wishlist items"
    )

    send_newsletter = models.BooleanField(
        default=True,
        help_text="Send newsletter emails"
    )

    send_promotional_emails = models.BooleanField(
        default=True,
        help_text="Send promotional/marketing emails"
    )

    # === SMS NOTIFICATIONS ===
    enable_sms = models.BooleanField(
        default=False,
        help_text="Enable SMS notifications"
    )

    sms_provider = models.CharField(
        max_length=20,
        choices=[
            ('twilio', 'Twilio'),
            ('nexmo', 'Nexmo/Vonage'),
            ('aws_sns', 'AWS SNS'),
            ('messagebird', 'MessageBird'),
            ('plivo', 'Plivo'),
        ],
        blank=True,
        help_text="SMS service provider"
    )

    sms_order_confirmation = models.BooleanField(
        default=False,
        help_text="Send SMS for order confirmation"
    )

    sms_order_shipped = models.BooleanField(
        default=True,
        help_text="Send SMS when order ships"
    )

    sms_order_delivered = models.BooleanField(
        default=False,
        help_text="Send SMS when order delivered"
    )

    sms_order_cancelled = models.BooleanField(
        default=True,
        help_text="Send SMS for order cancellation"
    )

    sms_verification_code = models.BooleanField(
        default=True,
        help_text="Send SMS verification codes"
    )

    # === ADMIN NOTIFICATIONS ===
    notify_admin_new_order = models.BooleanField(
        default=True,
        help_text="Notify admin of new orders"
    )

    notify_admin_low_stock = models.BooleanField(
        default=True,
        help_text="Notify admin when stock is low"
    )

    low_stock_threshold = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Stock level to trigger low stock alert"
    )

    notify_admin_out_of_stock = models.BooleanField(
        default=True,
        help_text="Notify admin when product out of stock"
    )

    notify_admin_new_review = models.BooleanField(
        default=True,
        help_text="Notify admin of new product reviews"
    )

    notify_admin_new_customer = models.BooleanField(
        default=False,
        help_text="Notify admin of new customer registrations"
    )

    notify_admin_failed_payment = models.BooleanField(
        default=True,
        help_text="Notify admin of failed payments"
    )

    notify_admin_refund_request = models.BooleanField(
        default=True,
        help_text="Notify admin of refund requests"
    )

    admin_notification_emails = models.JSONField(
        default=list,
        blank=True,
        help_text="List of admin emails to notify"
    )

    # === NOTIFICATION TIMING ===
    quiet_hours_enabled = models.BooleanField(
        default=False,
        help_text="Enable quiet hours (no notifications during this time)"
    )

    quiet_hours_start = models.TimeField(
        null=True,
        blank=True,
        help_text="Start of quiet hours (e.g., 22:00)"
    )

    quiet_hours_end = models.TimeField(
        null=True,
        blank=True,
        help_text="End of quiet hours (e.g., 08:00)"
    )

    respect_customer_timezone = models.BooleanField(
        default=True,
        help_text="Send notifications based on customer's timezone"
    )

    # === EMAIL PREFERENCES ===
    email_from_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Sender name for emails (defaults to store name)"
    )

    email_reply_to = models.EmailField(
        blank=True,
        help_text="Reply-to email address"
    )

    include_order_details_in_email = models.BooleanField(
        default=True,
        help_text="Include full order details in emails"
    )

    include_tracking_link = models.BooleanField(
        default=True,
        help_text="Include order tracking link in shipping emails"
    )

    # === PUSH NOTIFICATIONS ===
    enable_push_notifications = models.BooleanField(
        default=False,
        help_text="Enable browser/app push notifications"
    )

    push_order_updates = models.BooleanField(
        default=True,
        help_text="Send push notifications for order updates"
    )

    push_promotional = models.BooleanField(
        default=False,
        help_text="Send promotional push notifications"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_settings'
        verbose_name = 'Notification Setting'
        verbose_name_plural = 'Notification Settings'

    def __str__(self):
        return "Notification Settings"

    def clean(self):
        errors = {}

        if self.quiet_hours_enabled:
            if not self.quiet_hours_start or not self.quiet_hours_end:
                errors['quiet_hours_start'] = "Both start and end times required for quiet hours."

        if self.enable_sms and not self.sms_provider:
            errors['sms_provider'] = "SMS provider required when SMS is enabled."

        if errors:
            raise ValidationError(errors)


# ============================================================================
# 20. MOBILE APP SETTINGS - Mobile Application Configuration
# ============================================================================
class MobileAppSettings(models.Model):
    """
    Mobile app specific configurations.

    CONTROLS:
    - App theme and branding
    - Push notifications
    - App navigation
    - Offline mode
    - App-specific features

    IMPACT:
    - Mobile app user experience
    - App performance
    - Customer engagement
    """

    # === APP IDENTITY ===
    app_name = models.CharField(
        max_length=100,
        help_text="Mobile app name"
    )

    app_tagline = models.CharField(
        max_length=200,
        blank=True,
        help_text="App tagline/subtitle"
    )

    app_icon = models.ImageField(
        upload_to='mobile/icons/',
        blank=True,
        help_text="App icon (1024x1024px)"
    )

    splash_screen = models.ImageField(
        upload_to='mobile/splash/',
        blank=True,
        help_text="Splash screen image"
    )

    splash_screen_duration = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Splash screen display duration (seconds)"
    )

    # === THEME ===
    primary_color = models.CharField(
        max_length=7,
        default='#2563EB',
        help_text="Primary app color"
    )

    accent_color = models.CharField(
        max_length=7,
        default='#F59E0B',
        help_text="Accent color for highlights"
    )

    background_color = models.CharField(
        max_length=7,
        default='#FFFFFF',
        help_text="App background color"
    )

    status_bar_style = models.CharField(
        max_length=20,
        choices=[
            ('light', 'Light Content (for dark backgrounds)'),
            ('dark', 'Dark Content (for light backgrounds)'),
            ('auto', 'Auto (based on theme)'),
        ],
        default='auto'
    )

    enable_dark_mode = models.BooleanField(
        default=True,
        help_text="Support dark mode"
    )

    # === NAVIGATION ===
    bottom_nav_style = models.CharField(
        max_length=20,
        choices=[
            ('icons', 'Icons Only'),
            ('icons_labels', 'Icons with Labels'),
            ('labels', 'Labels Only'),
        ],
        default='icons_labels'
    )

    show_home_tab = models.BooleanField(default=True)
    show_categories_tab = models.BooleanField(default=True)
    show_search_tab = models.BooleanField(default=True)
    show_cart_tab = models.BooleanField(default=True)
    show_account_tab = models.BooleanField(default=True)
    show_wishlist_tab = models.BooleanField(default=False)

    max_bottom_nav_items = models.IntegerField(
        default=5,
        validators=[MinValueValidator(3), MaxValueValidator(6)],
        help_text="Maximum items in bottom navigation"
    )

    # === PUSH NOTIFICATIONS ===
    enable_push_notifications = models.BooleanField(
        default=True,
        help_text="Enable push notifications"
    )

    firebase_server_key = models.CharField(
        max_length=500,
        blank=True,
        help_text="Firebase Cloud Messaging server key"
    )

    apns_certificate = models.FileField(
        upload_to='mobile/certificates/',
        blank=True,
        help_text="Apple Push Notification Service certificate"
    )

    notify_order_updates = models.BooleanField(default=True)
    notify_promotions = models.BooleanField(default=True)
    notify_new_products = models.BooleanField(default=False)
    notify_price_drops = models.BooleanField(default=False)
    notify_back_in_stock = models.BooleanField(default=True)
    notify_abandoned_cart = models.BooleanField(default=True)

    # === FEATURES ===
    enable_biometric_login = models.BooleanField(
        default=True,
        help_text="Enable fingerprint/face ID login"
    )

    enable_offline_mode = models.BooleanField(
        default=False,
        help_text="Allow browsing in offline mode"
    )

    offline_cache_size_mb = models.IntegerField(
        default=50,
        validators=[MinValueValidator(10), MaxValueValidator(500)],
        help_text="Offline cache size in MB"
    )

    enable_barcode_scanner = models.BooleanField(
        default=False,
        help_text="Enable barcode/QR code scanner"
    )

    enable_ar_preview = models.BooleanField(
        default=False,
        help_text="Enable AR product preview"
    )

    enable_voice_search = models.BooleanField(
        default=False,
        help_text="Enable voice search"
    )

    enable_shake_to_refresh = models.BooleanField(
        default=True,
        help_text="Shake device to refresh"
    )

    # === PERFORMANCE ===
    image_quality = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Low (Faster Loading)'),
            ('medium', 'Medium (Balanced)'),
            ('high', 'High (Better Quality)'),
            ('auto', 'Auto (Based on Connection)'),
        ],
        default='auto'
    )

    enable_image_caching = models.BooleanField(
        default=True,
        help_text="Cache images locally"
    )

    cache_duration_hours = models.IntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
        help_text="Cache duration in hours"
    )

    enable_lazy_loading = models.BooleanField(
        default=True,
        help_text="Lazy load images and content"
    )

    # === DEEP LINKING ===
    android_package_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Android package name (e.g., com.store.app)"
    )

    ios_bundle_id = models.CharField(
        max_length=200,
        blank=True,
        help_text="iOS bundle identifier"
    )

    app_store_url = models.URLField(
        blank=True,
        help_text="Apple App Store URL"
    )

    play_store_url = models.URLField(
        blank=True,
        help_text="Google Play Store URL"
    )

    enable_universal_links = models.BooleanField(
        default=True,
        help_text="Enable universal/deep links"
    )

    # === ANALYTICS ===
    enable_app_analytics = models.BooleanField(
        default=True,
        help_text="Track app usage analytics"
    )

    enable_crash_reporting = models.BooleanField(
        default=True,
        help_text="Enable crash reporting"
    )

    # === APP UPDATES ===
    force_update_enabled = models.BooleanField(
        default=False,
        help_text="Force users to update to latest version"
    )

    minimum_app_version = models.CharField(
        max_length=20,
        blank=True,
        help_text="Minimum required app version (e.g., 1.0.0)"
    )

    show_update_prompt = models.BooleanField(
        default=True,
        help_text="Prompt users to update when new version available"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mobile_app_settings'
        verbose_name = 'Mobile App Setting'
        verbose_name_plural = 'Mobile App Settings'

    def __str__(self):
        return f"Mobile App Settings: {self.app_name}"


# ============================================================================
# 21. BLOG SETTINGS - Blog/Content Marketing Configuration
# ============================================================================
class BlogSettings(models.Model):
    """
    Blog and content marketing settings.

    CONTROLS:
    - Blog layout and display
    - Post settings
    - Comments and engagement
    - SEO for blog posts

    IMPACT:
    - Content marketing
    - SEO performance
    - Customer engagement

    SHOPIFY EQUIVALENT: Online Store > Blog posts
    """

    # === GENERAL ===
    enable_blog = models.BooleanField(
        default=True,
        help_text="Enable blog functionality"
    )

    blog_title = models.CharField(
        max_length=100,
        default='Blog',
        help_text="Blog section title"
    )

    blog_description = models.TextField(
        max_length=300,
        blank=True,
        help_text="Blog description for SEO"
    )

    blog_url_prefix = models.SlugField(
        max_length=50,
        default='blog',
        help_text="URL prefix for blog (e.g., /blog/)"
    )

    # === LAYOUT ===
    layout = models.CharField(
        max_length=20,
        choices=[
            ('grid', 'Grid Layout'),
            ('list', 'List Layout'),
            ('masonry', 'Masonry Grid'),
            ('magazine', 'Magazine Style'),
            ('cards', 'Card Style'),
        ],
        default='grid'
    )

    posts_per_page = models.IntegerField(
        default=12,
        validators=[MinValueValidator(6), MaxValueValidator(50)],
        help_text="Blog posts per page"
    )

    posts_per_row = models.IntegerField(
        default=3,
        choices=[(1, '1 Column'), (2, '2 Columns'), (3, '3 Columns'), (4, '4 Columns')],
        help_text="Posts per row in grid layout"
    )

    show_sidebar = models.BooleanField(
        default=True,
        help_text="Show sidebar on blog pages"
    )

    sidebar_position = models.CharField(
        max_length=10,
        choices=[('left', 'Left'), ('right', 'Right')],
        default='right'
    )

    # === POST DISPLAY ===
    show_featured_image = models.BooleanField(
        default=True,
        help_text="Show featured image on post listings"
    )

    featured_image_aspect_ratio = models.CharField(
        max_length=20,
        choices=[
            ('16_9', '16:9 (Landscape)'),
            ('4_3', '4:3'),
            ('1_1', '1:1 (Square)'),
            ('auto', 'Original'),
        ],
        default='16_9'
    )

    show_author = models.BooleanField(
        default=True,
        help_text="Show post author"
    )

    show_author_avatar = models.BooleanField(
        default=True,
        help_text="Show author profile picture"
    )

    show_date = models.BooleanField(
        default=True,
        help_text="Show publish date"
    )

    date_format = models.CharField(
        max_length=20,
        choices=[
            ('relative', 'Relative (2 days ago)'),
            ('short', 'Short (Jan 15, 2024)'),
            ('long', 'Long (January 15, 2024)'),
        ],
        default='short'
    )

    show_reading_time = models.BooleanField(
        default=True,
        help_text="Show estimated reading time"
    )

    show_excerpt = models.BooleanField(
        default=True,
        help_text="Show post excerpt/summary"
    )

    excerpt_length = models.IntegerField(
        default=150,
        validators=[MinValueValidator(50), MaxValueValidator(500)],
        help_text="Maximum excerpt length in characters"
    )

    show_read_more_button = models.BooleanField(
        default=True,
        help_text="Show 'Read More' button"
    )

    show_tags = models.BooleanField(
        default=True,
        help_text="Show post tags"
    )

    show_categories = models.BooleanField(
        default=True,
        help_text="Show post categories"
    )

    show_view_count = models.BooleanField(
        default=False,
        help_text="Show post view count"
    )

    # === SINGLE POST ===
    show_author_bio = models.BooleanField(
        default=True,
        help_text="Show author bio on single post"
    )

    show_share_buttons = models.BooleanField(
        default=True,
        help_text="Show social sharing buttons"
    )

    share_button_position = models.CharField(
        max_length=20,
        choices=[
            ('top', 'Top of Post'),
            ('bottom', 'Bottom of Post'),
            ('both', 'Top and Bottom'),
            ('floating', 'Floating Sidebar'),
        ],
        default='both'
    )

    show_related_posts = models.BooleanField(
        default=True,
        help_text="Show related posts"
    )

    related_posts_count = models.IntegerField(
        default=3,
        validators=[MinValueValidator(2), MaxValueValidator(12)]
    )

    show_post_navigation = models.BooleanField(
        default=True,
        help_text="Show previous/next post links"
    )

    # === COMMENTS ===
    enable_comments = models.BooleanField(
        default=True,
        help_text="Enable comments on blog posts"
    )

    comment_system = models.CharField(
        max_length=20,
        choices=[
            ('native', 'Native Comments'),
            ('disqus', 'Disqus'),
            ('facebook', 'Facebook Comments'),
            ('commento', 'Commento'),
            ('disabled', 'Disabled'),
        ],
        default='native'
    )

    require_approval = models.BooleanField(
        default=True,
        help_text="Require admin approval for comments"
    )

    require_login_to_comment = models.BooleanField(
        default=False,
        help_text="Require login to post comments"
    )

    show_comment_count = models.BooleanField(
        default=True,
        help_text="Show comment count on post listings"
    )

    # === SEO ===
    auto_generate_meta = models.BooleanField(
        default=True,
        help_text="Auto-generate meta descriptions from excerpt"
    )

    show_breadcrumbs = models.BooleanField(
        default=True,
        help_text="Show breadcrumb navigation"
    )

    enable_schema_markup = models.BooleanField(
        default=True,
        help_text="Add structured data (schema.org) markup"
    )

    # === SIDEBAR WIDGETS ===
    show_search_widget = models.BooleanField(default=True)
    show_categories_widget = models.BooleanField(default=True)
    show_recent_posts_widget = models.BooleanField(default=True)
    show_popular_posts_widget = models.BooleanField(default=True)
    show_tags_widget = models.BooleanField(default=True)
    show_newsletter_widget = models.BooleanField(default=True)

    recent_posts_count = models.IntegerField(default=5)
    popular_posts_count = models.IntegerField(default=5)

    # === RSS FEED ===
    enable_rss_feed = models.BooleanField(
        default=True,
        help_text="Enable RSS feed"
    )

    rss_posts_count = models.IntegerField(
        default=20,
        validators=[MinValueValidator(5), MaxValueValidator(100)],
        help_text="Number of posts in RSS feed"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'blog_settings'
        verbose_name = 'Blog Setting'
        verbose_name_plural = 'Blog Settings'

    def __str__(self):
        return f"Blog Settings: {self.blog_title}"



# ============================================================================
# 22. POPUP SETTINGS - Marketing Popups and Banners
# ============================================================================
class PopupSettings(models.Model):
    """
    Marketing popups and promotional banners configuration.

    CONTROLS:
    - Newsletter popups
    - Exit intent popups
    - Promotional banners
    - Cookie consent
    - Announcement bars

    IMPACT:
    - Lead generation
    - Marketing campaigns
    - Compliance (GDPR, cookies)
    """

    # === NEWSLETTER POPUP ===
    enable_newsletter_popup = models.BooleanField(
        default=False,
        help_text="Enable newsletter signup popup"
    )

    popup_title = models.CharField(
        max_length=100,
        default='Join Our Newsletter',
        help_text="Popup headline"
    )

    popup_description = models.TextField(
        max_length=300,
        default='Subscribe to get special offers, free giveaways, and exclusive deals.',
        help_text="Popup description text"
    )

    popup_image = models.ImageField(
        upload_to='popups/',
        blank=True,
        null=True,
        help_text="Popup background or side image"
    )

    popup_button_text = models.CharField(
        max_length=50,
        default='Subscribe'
    )

    show_discount_code = models.BooleanField(
        default=False,
        help_text="Offer discount code for subscribing"
    )

    discount_code_text = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., 'Get 10% off your first order!'"
    )

    # === TRIGGER SETTINGS ===
    trigger_type = models.CharField(
        max_length=20,
        choices=[
            ('time', 'Time Delay'),
            ('scroll', 'Scroll Percentage'),
            ('exit', 'Exit Intent'),
            ('immediate', 'Immediate'),
            ('click', 'On Click'),
        ],
        default='time',
        help_text="When to show popup"
    )

    trigger_delay_seconds = models.IntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(60)],
        help_text="Delay before showing popup (seconds)"
    )

    trigger_scroll_percentage = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Scroll percentage to trigger popup"
    )

    # === FREQUENCY ===
    show_once_per_session = models.BooleanField(
        default=False,
        help_text="Show only once per browser session"
    )

    show_once_per_days = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Don't show again for X days after closing"
    )

    show_to_subscribers = models.BooleanField(
        default=False,
        help_text="Show popup to existing subscribers"
    )

    show_on_mobile = models.BooleanField(
        default=True,
        help_text="Show popup on mobile devices"
    )

    # === APPEARANCE ===
    popup_position = models.CharField(
        max_length=20,
        choices=[
            ('center', 'Center'),
            ('bottom_right', 'Bottom Right'),
            ('bottom_left', 'Bottom Left'),
            ('bottom_center', 'Bottom Center'),
            ('top', 'Top Bar'),
            ('fullscreen', 'Fullscreen'),
        ],
        default='center'
    )

    popup_size = models.CharField(
        max_length=20,
        choices=[
            ('small', 'Small'),
            ('medium', 'Medium'),
            ('large', 'Large'),
        ],
        default='medium'
    )

    overlay_opacity = models.IntegerField(
        default=70,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Background overlay opacity (0-100%)"
    )

    popup_animation = models.CharField(
        max_length=20,
        choices=[
            ('fade', 'Fade In'),
            ('slide_up', 'Slide Up'),
            ('slide_down', 'Slide Down'),
            ('zoom', 'Zoom In'),
            ('none', 'No Animation'),
        ],
        default='fade'
    )

    enable_close_button = models.BooleanField(
        default=True,
        help_text="Show close (X) button"
    )

    close_on_overlay_click = models.BooleanField(
        default=True,
        help_text="Close popup when clicking outside"
    )

    # === COOKIE CONSENT ===
    enable_cookie_consent = models.BooleanField(
        default=True,
        help_text="Show cookie consent banner (GDPR compliance)"
    )

    cookie_message = models.TextField(
        max_length=300,
        default='We use cookies to improve your experience on our site. By using our site, you consent to cookies.',
        help_text="Cookie consent message"
    )

    cookie_button_text = models.CharField(
        max_length=50,
        default='Accept'
    )

    cookie_policy_url = models.URLField(
        blank=True,
        help_text="Link to cookie policy page"
    )

    cookie_banner_position = models.CharField(
        max_length=20,
        choices=[
            ('top', 'Top'),
            ('bottom', 'Bottom'),
            ('popup', 'Center Popup'),
        ],
        default='bottom'
    )

    show_cookie_settings = models.BooleanField(
        default=True,
        help_text="Allow users to customize cookie preferences"
    )

    # === PROMOTIONAL BANNER ===
    enable_promo_banner = models.BooleanField(
        default=False,
        help_text="Show promotional announcement banner"
    )

    promo_banner_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Banner text (e.g., 'Free shipping on orders over $50!')"
    )

    promo_banner_link = models.URLField(
        blank=True,
        help_text="Optional link when clicking banner"
    )

    promo_banner_background = models.CharField(
        max_length=7,
        default='#000000',
        help_text="Banner background color"
    )

    promo_banner_text_color = models.CharField(
        max_length=7,
        default='#FFFFFF',
        help_text="Banner text color"
    )

    promo_banner_position = models.CharField(
        max_length=10,
        choices=[('top', 'Top'), ('bottom', 'Bottom')],
        default='top'
    )

    promo_banner_dismissible = models.BooleanField(
        default=True,
        help_text="Allow users to close banner"
    )

    promo_banner_sticky = models.BooleanField(
        default=True,
        help_text="Keep banner visible when scrolling"
    )

    # === EXIT INTENT ===
    enable_exit_intent = models.BooleanField(
        default=False,
        help_text="Show popup when user attempts to leave"
    )

    exit_intent_title = models.CharField(
        max_length=100,
        default='Wait! Before you go...',
        blank=True
    )

    exit_intent_message = models.TextField(
        max_length=300,
        blank=True,
        help_text="Exit intent popup message"
    )

    exit_intent_offer = models.CharField(
        max_length=100,
        blank=True,
        help_text="Special offer (e.g., '10% off your first order')"
    )

    # === A/B TESTING ===
    enable_ab_testing = models.BooleanField(
        default=False,
        help_text="Enable A/B testing for popups"
    )

    variant_a_title = models.CharField(max_length=100, blank=True)
    variant_b_title = models.CharField(max_length=100, blank=True)

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'popup_settings'
        verbose_name = 'Popup Setting'
        verbose_name_plural = 'Popup Settings'

    def __str__(self):
        return "Popup Settings"


# ============================================================================
# 23. PERFORMANCE SETTINGS - Site Performance Optimization
# ============================================================================
class PerformanceSettings(models.Model):
    """
    Site performance and optimization settings.

    CONTROLS:
    - Caching configuration
    - Image optimization
    - Code minification
    - CDN settings
    - Lazy loading

    IMPACT:
    - Page load speed
    - SEO rankings
    - User experience
    - Server resources
    """

    # === CACHING ===
    enable_page_cache = models.BooleanField(
        default=True,
        help_text="Enable full page caching"
    )

    cache_duration_minutes = models.IntegerField(
        default=60,
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
        help_text="Page cache duration in minutes"
    )

    enable_browser_cache = models.BooleanField(
        default=True,
        help_text="Enable browser caching headers"
    )

    browser_cache_duration_days = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Browser cache duration in days"
    )

    enable_database_query_cache = models.BooleanField(
        default=True,
        help_text="Cache database queries"
    )

    cache_products = models.BooleanField(
        default=True,
        help_text="Cache product data"
    )

    cache_categories = models.BooleanField(
        default=True,
        help_text="Cache category data"
    )

    cache_settings = models.BooleanField(
        default=True,
        help_text="Cache store settings"
    )

    # === IMAGE OPTIMIZATION ===
    enable_lazy_loading = models.BooleanField(
        default=True,
        help_text="Lazy load images (load as they enter viewport)"
    )

    enable_webp = models.BooleanField(
        default=True,
        help_text="Convert images to WebP format"
    )

    webp_quality = models.IntegerField(
        default=85,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="WebP image quality (1-100)"
    )

    enable_image_compression = models.BooleanField(
        default=True,
        help_text="Compress images automatically"
    )

    image_quality = models.IntegerField(
        default=85,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="JPEG/PNG compression quality (1-100)"
    )

    enable_responsive_images = models.BooleanField(
        default=True,
        help_text="Generate multiple image sizes for different devices"
    )

    max_image_width = models.IntegerField(
        default=2000,
        validators=[MinValueValidator(800), MaxValueValidator(4000)],
        help_text="Maximum image width in pixels"
    )

    # === MINIFICATION ===
    minify_html = models.BooleanField(
        default=True,
        help_text="Minify HTML output"
    )

    minify_css = models.BooleanField(
        default=True,
        help_text="Minify CSS files"
    )

    minify_js = models.BooleanField(
        default=True,
        help_text="Minify JavaScript files"
    )

    combine_css = models.BooleanField(
        default=True,
        help_text="Combine multiple CSS files into one"
    )

    combine_js = models.BooleanField(
        default=True,
        help_text="Combine multiple JS files into one"
    )

    # === CDN ===
    enable_cdn = models.BooleanField(
        default=False,
        help_text="Use Content Delivery Network"
    )

    cdn_provider = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('cloudflare', 'Cloudflare'),
            ('aws_cloudfront', 'AWS CloudFront'),
            ('fastly', 'Fastly'),
            ('bunny', 'BunnyCDN'),
            ('custom', 'Custom CDN'),
        ],
        help_text="CDN provider"
    )

    cdn_url = models.URLField(
        blank=True,
        help_text="CDN base URL (e.g., https://cdn.example.com)"
    )

    cdn_for_images = models.BooleanField(
        default=True,
        help_text="Serve images through CDN"
    )

    cdn_for_css = models.BooleanField(
        default=True,
        help_text="Serve CSS through CDN"
    )

    cdn_for_js = models.BooleanField(
        default=True,
        help_text="Serve JavaScript through CDN"
    )

    # === PRELOADING ===
    enable_dns_prefetch = models.BooleanField(
        default=True,
        help_text="Enable DNS prefetching for external resources"
    )

    enable_preconnect = models.BooleanField(
        default=True,
        help_text="Preconnect to required origins"
    )

    enable_prefetch = models.BooleanField(
        default=False,
        help_text="Prefetch next page resources"
    )

    # === COMPRESSION ===
    enable_gzip = models.BooleanField(
        default=True,
        help_text="Enable Gzip compression"
    )

    enable_brotli = models.BooleanField(
        default=True,
        help_text="Enable Brotli compression (better than Gzip)"
    )

    # === DATABASE ===
    enable_database_connection_pooling = models.BooleanField(
        default=True,
        help_text="Use database connection pooling"
    )

    max_database_connections = models.IntegerField(
        default=20,
        validators=[MinValueValidator(5), MaxValueValidator(100)],
        help_text="Maximum database connections"
    )

    # === MONITORING ===
    enable_performance_monitoring = models.BooleanField(
        default=True,
        help_text="Monitor page load times"
    )

    log_slow_queries = models.BooleanField(
        default=True,
        help_text="Log slow database queries"
    )

    slow_query_threshold_ms = models.IntegerField(
        default=1000,
        validators=[MinValueValidator(100), MaxValueValidator(10000)],
        help_text="Threshold for slow query logging (milliseconds)"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'performance_settings'
        verbose_name = 'Performance Setting'
        verbose_name_plural = 'Performance Settings'

    def __str__(self):
        return "Performance Settings"


# ============================================================================
# SIGNALS - Auto-initialization for New Tenants
# ============================================================================

@receiver(post_migrate)
def initialize_store_settings(sender, **kwargs):
    """
    Initialize default settings for tenant after migration.
    Creates singleton instances of all settings models.

    This signal runs after tenant schema migrations complete.
    """
    # Only run for tenant apps, not public schema
    if sender.name != 'dashboard.store_settings':
        return

    try:
        # Check if we're in a tenant schema (not public)
        if connection.schema_name == 'public':
            logger.info("Skipping settings initialization for public schema")
            return

        logger.info(f"Initializing store settings for tenant: {connection.schema_name}")

        # 1. Store Settings (Core)
        if not StoreSettings.objects.exists():
            StoreSettings.objects.create(
                store_name=f"Store - {connection.schema_name}",
                contact_email="contact@example.com"
            )
            logger.info("✓ Created StoreSettings")

        # 2. Theme Settings
        if not ThemeSettings.objects.exists():
            ThemeSettings.objects.create(
                theme_name="Default Theme",
                is_active=True
            )
            logger.info("✓ Created ThemeSettings")

        # 3. Header Settings
        if not HeaderSettings.objects.exists():
            HeaderSettings.objects.create()
            logger.info("✓ Created HeaderSettings")

        # 4. Footer Settings
        if not FooterSettings.objects.exists():
            FooterSettings.objects.create()
            logger.info("✓ Created FooterSettings")

        # 5. Homepage Layout
        if not HomepageLayout.objects.exists():
            HomepageLayout.objects.create()
            logger.info("✓ Created HomepageLayout")

        # 6. Product Display Settings
        if not ProductDisplaySettings.objects.exists():
            ProductDisplaySettings.objects.create()
            logger.info("✓ Created ProductDisplaySettings")

        # 7. Product Page Settings
        if not ProductPageSettings.objects.exists():
            ProductPageSettings.objects.create()
            logger.info("✓ Created ProductPageSettings")

        # 8. Cart Settings
        if not CartSettings.objects.exists():
            CartSettings.objects.create()
            logger.info("✓ Created CartSettings")

        # 9. Checkout Settings
        if not CheckoutSettings.objects.exists():
            CheckoutSettings.objects.create()
            logger.info("✓ Created CheckoutSettings")

        # 10. Search Settings
        if not SearchSettings.objects.exists():
            SearchSettings.objects.create()
            logger.info("✓ Created SearchSettings")

        # 11. Email Template Settings
        if not EmailTemplateSettings.objects.exists():
            EmailTemplateSettings.objects.create()
            logger.info("✓ Created EmailTemplateSettings")

        # 12. Social Media Links
        if not SocialMediaLinks.objects.exists():
            SocialMediaLinks.objects.create()
            logger.info("✓ Created SocialMediaLinks")

        # 13. Notification Settings
        if not NotificationSettings.objects.exists():
            NotificationSettings.objects.create()
            logger.info("✓ Created NotificationSettings")

        # 14. Mobile App Settings
        if not MobileAppSettings.objects.exists():
            MobileAppSettings.objects.create(
                app_name=f"Store App - {connection.schema_name}"
            )
            logger.info("✓ Created MobileAppSettings")

        # 15. Blog Settings
        if not BlogSettings.objects.exists():
            BlogSettings.objects.create()
            logger.info("✓ Created BlogSettings")

        # 16. Popup Settings
        if not PopupSettings.objects.exists():
            PopupSettings.objects.create()
            logger.info("✓ Created PopupSettings")

        # 17. Performance Settings
        if not PerformanceSettings.objects.exists():
            PerformanceSettings.objects.create()
            logger.info("✓ Created PerformanceSettings")

        # 18. Create default navigation menu
        if not NavigationMenu.objects.filter(location='header').exists():
            NavigationMenu.objects.create(
                name='Main Menu',
                location='header',
                is_active=True
            )
            logger.info("✓ Created default navigation menu")

        logger.info(f"✅ Store settings initialization complete for {connection.schema_name}")

    except Exception as e:
        logger.error(f"❌ Error initializing store settings: {str(e)}")


# Cache invalidation signals
@receiver(post_save, sender=StoreSettings)
@receiver(post_save, sender=ThemeSettings)
@receiver(post_save, sender=HeaderSettings)
@receiver(post_save, sender=FooterSettings)
def invalidate_settings_cache(sender, instance, **kwargs):
    """Invalidate cache when settings are updated."""
    cache_key = f'store_settings_{connection.schema_name}'
    cache.delete(cache_key)
    logger.debug(f"Cache invalidated for {sender.__name__}")


@receiver(post_delete, sender=StoreSettings)
@receiver(post_delete, sender=ThemeSettings)
def invalidate_settings_cache_on_delete(sender, instance, **kwargs):
    """Invalidate cache when settings are deleted."""
    cache_key = f'store_settings_{connection.schema_name}'
    cache.delete(cache_key)
    logger.debug(f"Cache invalidated on delete for {sender.__name__}")
