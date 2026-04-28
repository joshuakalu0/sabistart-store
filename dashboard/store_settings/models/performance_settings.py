from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


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


