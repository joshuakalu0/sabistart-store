"""
Professional Store Settings System
Consolidated, robust settings architecture for multi-tenant e-commerce

Design Philosophy:
- Single source of truth with organized field groups
- Comprehensive validation and business logic
- Performance-optimized with caching
- Clean API for settings access
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, URLValidator, EmailValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.functional import cached_property
from decimal import Decimal
import re


class StoreSettingsManager(models.Manager):
    """Custom manager for singleton pattern enforcement."""

    def get_settings(self):
        """Get or create the singleton settings instance."""
        if self.exists():
            return self.first()
        else:
            # Create new instance with required fields
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
    )  # TODO: Add to form
    store_description = models.TextField(
        blank=True,
        help_text="Full store description"
    )  # TODO: Add to form

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
    default_language = models.CharField(
        max_length=10,
        default='en',
        help_text="ISO language code (e.g., 'en', 'fr', 'es')"
    )
    default_currency = models.CharField(
        max_length=3,
        default='USD',
        help_text="ISO currency code (e.g., 'USD', 'EUR', 'GBP')"
    )
    currency_position = models.CharField(
        max_length=10, choices=[('left', 'Left'), ('right', 'Right')], default='left')
    time_zone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="IANA time zone (e.g., 'America/New_York')"
    )

    # Operational Status
    STORE_STATUS_CHOICES = [
        ('active', 'Active'),
        ('maintenance', 'Maintenance Mode'),
        ('closed', 'Temporarily Closed'),
    ]
    store_status = models.CharField(
        max_length=20,
        choices=STORE_STATUS_CHOICES,
        default='active',
        db_index=True
    )
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

    # Business Model
    BUSINESS_MODEL_CHOICES = [
        ('single', 'Single Vendor'),
        ('multi', 'Multi Vendor'),
    ]
    business_model = models.CharField(
        max_length=20,
        choices=BUSINESS_MODEL_CHOICES,
        default='multi',
        help_text="Business model type"
    )

    # Social Media
    facebook_url = models.URLField(
        blank=True,
        help_text="Facebook profile URL"
    )
    instagram_url = models.URLField(
        blank=True,
        help_text="Instagram profile URL"
    )
    twitter_url = models.URLField(
        blank=True,
        help_text="Twitter profile URL"
    )
    linkedin_url = models.URLField(
        blank=True,
        help_text="LinkedIn company URL"
    )

    # Copyright
    copyright_text = models.CharField(
        max_length=255,
        default='Copyright © %Y Your Company. All Rights Reserved.',
        help_text="Copyright text for footer"
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

    # Colors (hex codes)
    primary_color = models.CharField(
        max_length=7,
        default='#2563EB',
        help_text="Primary brand color (hex)"
    )
    secondary_color = models.CharField(
        max_length=7,
        default='#64748B',
        help_text="Secondary color (hex)"
    )
    accent_color = models.CharField(
        max_length=7,
        default='#F59E0B',
        help_text="Accent color (hex)"
    )
    background_color = models.CharField(
        max_length=7,
        default='#FFFFFF',
        help_text="Background color (hex)"
    )
    text_color = models.CharField(
        max_length=7,
        default='#1F2937',
        help_text="Text color (hex)"
    )

    # Typography
    heading_font = models.CharField(
        max_length=100,
        default='Inter',
        help_text="Font for headings"
    )
    body_font = models.CharField(
        max_length=100,
        default='Inter',
        help_text="Font for body text"
    )

    # Layout
    LAYOUT_STYLE_CHOICES = [
        ('modern', 'Modern'),
        ('classic', 'Classic'),
        ('minimal', 'Minimal'),
    ]
    layout_style = models.CharField(
        max_length=20,
        choices=LAYOUT_STYLE_CHOICES,
        default='modern'
    )

    # ============================================
    # SEO & ANALYTICS
    # ============================================

    # Domain
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        help_text="Custom domain (e.g., shop.com)"
    )

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

    # Open Graph
    og_title = models.CharField(
        max_length=60,
        blank=True,
        help_text="Open Graph title"
    )
    og_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="Open Graph description"
    )
    og_image = models.ImageField(
        upload_to='seo/og/',
        blank=True,
        help_text="Open Graph image (1200x630)"
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
    # PAYMENT SETTINGS
    # ============================================

    # Mode
    payment_test_mode = models.BooleanField(
        default=True,
        help_text="Enable test/sandbox mode"
    )

    # Stripe
    stripe_enabled = models.BooleanField(default=False)
    stripe_publishable_key = models.CharField(max_length=255, blank=True)
    stripe_secret_key = models.CharField(max_length=255, blank=True)
    stripe_webhook_secret = models.CharField(max_length=255, blank=True)

    # PayPal
    paypal_enabled = models.BooleanField(default=False)
    paypal_client_id = models.CharField(max_length=255, blank=True)
    paypal_secret = models.CharField(max_length=255, blank=True)

    # Other Methods
    cash_on_delivery_enabled = models.BooleanField(default=False)
    bank_transfer_enabled = models.BooleanField(default=False)

    # Payment Options
    default_payment_method = models.CharField(
        max_length=50,
        default='stripe',
        help_text="Default payment method"
    )
    accept_partial_payments = models.BooleanField(
        default=False,
        help_text="Allow partial payments"
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

    # Flat Rate
    flat_rate_enabled = models.BooleanField(default=False)
    flat_rate_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
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

    # ============================================
    # NOTIFICATION SETTINGS
    # ============================================

    # Email Settings
    email_notifications_enabled = models.BooleanField(default=True)
    from_email = models.EmailField(
        blank=True,
        help_text="Sender email address"
    )
    from_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Sender name"
    )

    # Order Notifications (Staff)
    notify_new_order = models.BooleanField(
        default=True,
        help_text="Notify staff of new orders"
    )
    notify_order_shipped = models.BooleanField(default=True)
    notify_order_delivered = models.BooleanField(default=True)
    notify_order_cancelled = models.BooleanField(default=True)

    # Customer Notifications
    send_order_confirmation = models.BooleanField(default=True)
    send_shipping_confirmation = models.BooleanField(default=True)
    send_delivery_confirmation = models.BooleanField(default=True)

    # Inventory Alerts
    low_stock_alert_enabled = models.BooleanField(default=True)
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(0)]
    )
    out_of_stock_alert_enabled = models.BooleanField(default=True)

    # SMS Settings
    sms_notifications_enabled = models.BooleanField(default=False)
    sms_provider = models.CharField(max_length=50, blank=True)

    # ============================================
    # POLICY SETTINGS
    # ============================================

    privacy_policy = models.TextField(blank=True)
    terms_of_service = models.TextField(blank=True)
    refund_policy = models.TextField(blank=True)
    shipping_policy = models.TextField(blank=True)

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

    # Required Fields
    require_phone = models.BooleanField(default=True)
    require_company = models.BooleanField(default=False)
    require_address_line2 = models.BooleanField(default=False)

    # Cart Settings
    cart_expiry_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Days before cart expires"
    )
    show_cart_on_add = models.BooleanField(
        default=True,
        help_text="Show cart after adding item"
    )

    # Order Settings
    allow_order_notes = models.BooleanField(default=True)
    require_order_notes = models.BooleanField(default=False)

    # Validation
    validate_address = models.BooleanField(
        default=False,
        help_text="Use address validation service"
    )

    # Minimum Order
    minimum_order_enabled = models.BooleanField(default=False)
    minimum_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    # ============================================
    # SECURITY SETTINGS
    # ============================================

    # Password Policy
    min_password_length = models.PositiveIntegerField(
        default=8,
        validators=[MinValueValidator(6), MaxValueValidator(128)]
    )
    require_uppercase = models.BooleanField(default=True)
    require_lowercase = models.BooleanField(default=True)
    require_numbers = models.BooleanField(default=True)
    require_special_chars = models.BooleanField(default=False)

    # Session Management
    session_timeout_minutes = models.PositiveIntegerField(
        default=60,
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
        help_text="Staff session timeout"
    )
    customer_session_timeout_minutes = models.PositiveIntegerField(
        default=1440,
        validators=[MinValueValidator(5), MaxValueValidator(10080)]
    )

    # Two-Factor Authentication
    enable_2fa = models.BooleanField(
        default=False,
        help_text="Enable 2FA for staff"
    )
    require_2fa_for_staff = models.BooleanField(default=False)

    # Account Security
    max_login_attempts = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(3), MaxValueValidator(10)]
    )
    lockout_duration_minutes = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(1440)]
    )
    dashboard_path_prefix = models.CharField(max_length=255, default='admin')

    # Data Protection
    enable_gdpr_mode = models.BooleanField(
        default=False,
        help_text="GDPR compliance features"
    )
    data_retention_days = models.PositiveIntegerField(
        default=365,
        validators=[MinValueValidator(30), MaxValueValidator(3650)]
    )

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
    enable_newsletter = models.BooleanField(default=True)
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

        # Validate currency code
        if self.default_currency and len(self.default_currency) != 3:
            errors['default_currency'] = "Currency code must be 3 characters (ISO 4217)."

        # Validate language code
        if self.default_language and len(self.default_language) > 10:
            errors['default_language'] = "Language code is too long."

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

        # Validate payment settings
        if self.stripe_enabled and not self.stripe_secret_key:
            errors['stripe_secret_key'] = "Stripe secret key is required when Stripe is enabled."
        if self.paypal_enabled and not self.paypal_client_id:
            errors['paypal_client_id'] = "PayPal client ID is required when PayPal is enabled."

        # Validate shipping threshold
        if self.free_shipping_enabled and self.free_shipping_threshold <= 0:
            errors['free_shipping_threshold'] = "Free shipping threshold must be greater than 0."

        # Validate minimum order
        if self.minimum_order_enabled and self.minimum_order_amount <= 0:
            errors['minimum_order_amount'] = "Minimum order amount must be greater than 0."

        # Validate tax rate
        if self.tax_enabled and self.default_tax_rate < 0:
            errors['default_tax_rate'] = "Tax rate cannot be negative."

        # Validate password policy
        if self.min_password_length < 6:
            errors['min_password_length'] = "Minimum password length should be at least 6 characters."

        # Validate session timeouts
        if self.session_timeout_minutes < 5:
            errors['session_timeout_minutes'] = "Session timeout must be at least 5 minutes."

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
        return self.maintenance_mode or self.store_status == 'maintenance'

    @cached_property
    def is_operational(self):
        """Check if store is operational."""
        return self.store_status == 'active' and not self.maintenance_mode

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
        return (
            self.stripe_enabled or
            self.paypal_enabled or
            self.cash_on_delivery_enabled or
            self.bank_transfer_enabled
        )

    @cached_property
    def has_shipping_method(self):
        """Check if any shipping method is configured."""
        return (
            self.shipping_enabled and (
                self.free_shipping_enabled or
                self.flat_rate_enabled or
                self.use_live_rates
            )
        )

    def get_active_payment_methods(self):
        """Get list of active payment methods."""
        methods = []
        if self.stripe_enabled:
            methods.append('stripe')
        if self.paypal_enabled:
            methods.append('paypal')
        if self.cash_on_delivery_enabled:
            methods.append('cash_on_delivery')
        if self.bank_transfer_enabled:
            methods.append('bank_transfer')
        return methods

    def validate_password(self, password):
        """Validate password against policy."""
        errors = []

        if len(password) < self.min_password_length:
            errors.append(
                f"Password must be at least {self.min_password_length} characters.")

        if self.require_uppercase and not re.search(r'[A-Z]', password):
            errors.append(
                "Password must contain at least one uppercase letter.")

        if self.require_lowercase and not re.search(r'[a-z]', password):
            errors.append(
                "Password must contain at least one lowercase letter.")

        if self.require_numbers and not re.search(r'\d', password):
            errors.append("Password must contain at least one number.")

        if self.require_special_chars and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append(
                "Password must contain at least one special character.")

        return errors

    class Meta:
        db_table = 'store_settings_consolidated'
        verbose_name = 'Store Settings'
        verbose_name_plural = 'Store Settings'
