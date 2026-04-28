import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import PerformanceSettings

logger = logging.getLogger(__name__)


class PerformanceSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Performance Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = PerformanceSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === CACHING ===
            'enable_page_cache': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cache_duration_minutes': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 5,
                'max': 1440
            }),
            'enable_browser_cache': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'browser_cache_duration_days': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 365
            }),
            'enable_database_query_cache': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cache_products': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cache_categories': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cache_settings': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === IMAGE OPTIMIZATION ===
            'enable_lazy_loading': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'enable_webp': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'webp_quality': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 100
            }),
            'enable_image_compression': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'image_quality': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 100
            }),
            'enable_responsive_images': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'max_image_width': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 800,
                'max': 4000
            }),

            # === MINIFICATION ===
            'minify_html': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'minify_css': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'minify_js': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'combine_css': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'combine_js': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === CDN ===
            'enable_cdn': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cdn_provider': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'cdn_url': forms.URLInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'https://cdn.example.com'
            }),
            'cdn_for_images': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cdn_for_css': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cdn_for_js': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === PRELOADING ===
            'enable_dns_prefetch': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'enable_preconnect': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'enable_prefetch': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === COMPRESSION ===
            'enable_gzip': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'enable_brotli': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === DATABASE ===
            'enable_database_connection_pooling': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'max_database_connections': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 5,
                'max': 100
            }),

            # === MONITORING ===
            'enable_performance_monitoring': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'log_slow_queries': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'slow_query_threshold_ms': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 100,
                'max': 10000
            }),
        }

    def clean_cache_duration_minutes(self):
        """Validate cache duration range."""
        duration = self.cleaned_data.get('cache_duration_minutes')
        if duration and not (5 <= duration <= 1440):
            raise ValidationError(
                _("Cache duration must be between 5 and 1440 minutes."))
        return duration

    def clean_browser_cache_duration_days(self):
        """Validate browser cache duration range."""
        days = self.cleaned_data.get('browser_cache_duration_days')
        if days and not (1 <= days <= 365):
            raise ValidationError(
                _("Browser cache duration must be between 1 and 365 days."))
        return days

    def clean_webp_quality(self):
        """Validate WebP quality range."""
        quality = self.cleaned_data.get('webp_quality')
        if quality and not (1 <= quality <= 100):
            raise ValidationError(_("WebP quality must be between 1 and 100."))
        return quality

    def clean_image_quality(self):
        """Validate image quality range."""
        quality = self.cleaned_data.get('image_quality')
        if quality and not (1 <= quality <= 100):
            raise ValidationError(
                _("Image quality must be between 1 and 100."))
        return quality

    def clean_max_image_width(self):
        """Validate max image width range."""
        width = self.cleaned_data.get('max_image_width')
        if width and not (800 <= width <= 4000):
            raise ValidationError(
                _("Max image width must be between 800 and 4000 pixels."))
        return width

    def clean_max_database_connections(self):
        """Validate max database connections range."""
        connections = self.cleaned_data.get('max_database_connections')
        if connections and not (5 <= connections <= 100):
            raise ValidationError(
                _("Max database connections must be between 5 and 100."))
        return connections

    def clean_slow_query_threshold_ms(self):
        """Validate slow query threshold range."""
        threshold = self.cleaned_data.get('slow_query_threshold_ms')
        if threshold and not (100 <= threshold <= 10000):
            raise ValidationError(
                _("Slow query threshold must be between 100 and 10000 milliseconds."))
        return threshold

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === CDN Logic ===
        cdn_enabled = cleaned_data.get('enable_cdn')
        cdn_url = cleaned_data.get('cdn_url')
        cdn_provider = cleaned_data.get('cdn_provider')

        if cdn_enabled and not cdn_url:
            self.add_error(
                'cdn_url',
                _("CDN URL is required when CDN is enabled.")
            )

        if cdn_enabled and not cdn_provider:
            self.add_error(
                'cdn_provider',
                _("CDN provider is required when CDN is enabled.")
            )

        if not cdn_enabled:
            logger.info("CDN disabled - CDN-specific settings will be ignored")

        # === WebP Logic ===
        webp_enabled = cleaned_data.get('enable_webp')
        webp_quality = cleaned_data.get('webp_quality')

        if webp_enabled and not webp_quality:
            self.add_error(
                'webp_quality',
                _("WebP quality is required when WebP conversion is enabled.")
            )

        # === Image Compression Logic ===
        compression_enabled = cleaned_data.get('enable_image_compression')
        image_quality = cleaned_data.get('image_quality')

        if compression_enabled and not image_quality:
            self.add_error(
                'image_quality',
                _("Image quality is required when compression is enabled.")
            )

        # === Minification Logic ===
        minify_css = cleaned_data.get('minify_css')
        combine_css = cleaned_data.get('combine_css')
        minify_js = cleaned_data.get('minify_js')
        combine_js = cleaned_data.get('combine_js')

        if combine_css and not minify_css:
            logger.warning(
                "Combine CSS enabled but minify CSS disabled - may reduce optimization benefits")

        if combine_js and not minify_js:
            logger.warning(
                "Combine JS enabled but minify JS disabled - may reduce optimization benefits")

        # === Compression Logic ===
        gzip_enabled = cleaned_data.get('enable_gzip')
        brotli_enabled = cleaned_data.get('enable_brotli')

        if gzip_enabled and brotli_enabled:
            logger.info(
                "Both Gzip and Brotli enabled - Brotli will take precedence for supporting browsers")

        if not gzip_enabled and not brotli_enabled:
            logger.warning(
                "Both Gzip and Brotli disabled - this may significantly impact page load times")

        # === Database Logic ===
        db_pooling = cleaned_data.get('enable_database_connection_pooling')
        max_connections = cleaned_data.get('max_database_connections')

        if db_pooling and not max_connections:
            self.add_error(
                'max_database_connections',
                _("Max database connections is required when connection pooling is enabled.")
            )

        # === Monitoring Logic ===
        log_slow = cleaned_data.get('log_slow_queries')
        slow_threshold = cleaned_data.get('slow_query_threshold_ms')

        if log_slow and not slow_threshold:
            self.add_error(
                'slow_query_threshold_ms',
                _("Slow query threshold is required when slow query logging is enabled.")
            )

        # === Caching Logic ===
        page_cache = cleaned_data.get('enable_page_cache')
        cache_duration = cleaned_data.get('cache_duration_minutes')

        if page_cache and not cache_duration:
            self.add_error(
                'cache_duration_minutes',
                _("Cache duration is required when page caching is enabled.")
            )

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"PerformanceSettings saved (tenant schema: {instance._meta.db_table})"
        )
        return instance
