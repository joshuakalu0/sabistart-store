"""Utility functions for settings management."""

from django.core.cache import cache
from store_settings.models import (
    GeneralSettings, BrandingSettings, SEOSettings,
    PaymentSettings, ShippingSettings, TaxSettings,
    NotificationSettings, PolicySettings, CheckoutSettings,
    SecuritySettings, FeatureSettings
)


def get_cached_settings(model_class, cache_key, timeout=3600):
    """Get settings with caching."""
    settings = cache.get(cache_key)
    if not settings:
        settings = model_class.objects.first()
        if not settings:
            settings = model_class.objects.create()
        cache.set(cache_key, settings, timeout)
    return settings


def invalidate_settings_cache(cache_key):
    """Invalidate cached settings."""
    cache.delete(cache_key)


def export_settings_to_dict():
    """Export all settings to dictionary."""
    from store_settings.utils import get_all_settings
    from django.forms.models import model_to_dict
    
    all_settings = get_all_settings()
    return {
        key: model_to_dict(value, exclude=['id', 'created_at', 'updated_at'])
        for key, value in all_settings.items()
    }


def validate_payment_credentials(settings):
    """Validate payment gateway credentials."""
    errors = []
    
    if settings.stripe_enabled:
        if not settings.stripe_publishable_key:
            errors.append("Stripe publishable key is required")
        if not settings.stripe_secret_key:
            errors.append("Stripe secret key is required")
    
    if settings.paypal_enabled:
        if not settings.paypal_client_id:
            errors.append("PayPal client ID is required")
        if not settings.paypal_secret:
            errors.append("PayPal secret is required")
    
    return errors


def validate_shipping_settings(settings):
    """Validate shipping configuration."""
    errors = []
    
    if settings.free_shipping_enabled and settings.free_shipping_threshold <= 0:
        errors.append("Free shipping threshold must be greater than 0")
    
    if settings.flat_rate_enabled and settings.flat_rate_amount < 0:
        errors.append("Flat rate amount cannot be negative")
    
    return errors


def get_active_payment_methods(settings):
    """Get list of active payment methods."""
    methods = []
    
    if settings.stripe_enabled:
        methods.append('stripe')
    if settings.paypal_enabled:
        methods.append('paypal')
    if settings.cash_on_delivery_enabled:
        methods.append('cod')
    if settings.bank_transfer_enabled:
        methods.append('bank_transfer')
    
    return methods


def calculate_tax_amount(subtotal, tax_settings):
    """Calculate tax amount based on settings."""
    if not tax_settings.tax_enabled:
        return 0
    
    tax_rate = tax_settings.default_tax_rate / 100
    return subtotal * tax_rate


def is_feature_enabled(feature_name):
    """Check if a feature is enabled."""
    from store_settings.utils import get_feature_settings
    settings = get_feature_settings()
    return getattr(settings, f'enable_{feature_name}', False)
