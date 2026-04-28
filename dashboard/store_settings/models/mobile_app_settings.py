from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


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


