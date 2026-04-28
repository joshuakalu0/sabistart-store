import uuid
import logging
import re
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, EmailValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.functional import cached_property
from decimal import Decimal
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)


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

    # currency_position = models.CharField(
    #     max_length=100,
    # choices=[
    #     ('before', 'Before ($100)'),
    #     ('after', 'After (100$)'),
    #     ('before_space', 'Before with space ($ 100)'),
    #     ('after_space', 'After with space (100 $)'),
    # ],
    #     default='before'
    # )

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
        app_label = 'store_settings'
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
