"""
Settings Helper Utilities
Singleton pattern implementation for settings retrieval
"""

from .models import (
    GeneralSettings, BrandingSettings, SEOSettings,
    PaymentSettings, ShippingSettings, TaxSettings,
    NotificationSettings, PolicySettings, CheckoutSettings,
    SecuritySettings, FeatureSettings
)


def get_general_settings():
    """Get or create general settings (singleton per tenant)."""
    settings, created = GeneralSettings.objects.get_or_create(
        pk=GeneralSettings.objects.first().pk if GeneralSettings.objects.exists() else None
    )
    return settings


def get_branding_settings():
    """Get or create branding settings (singleton per tenant)."""
    settings, created = BrandingSettings.objects.get_or_create(
        pk=BrandingSettings.objects.first().pk if BrandingSettings.objects.exists() else None
    )
    return settings


def get_seo_settings():
    """Get or create SEO settings (singleton per tenant)."""
    settings, created = SEOSettings.objects.get_or_create(
        pk=SEOSettings.objects.first().pk if SEOSettings.objects.exists() else None
    )
    return settings


def get_payment_settings():
    """Get or create payment settings (singleton per tenant)."""
    settings, created = PaymentSettings.objects.get_or_create(
        pk=PaymentSettings.objects.first().pk if PaymentSettings.objects.exists() else None
    )
    return settings


def get_shipping_settings():
    """Get or create shipping settings (singleton per tenant)."""
    settings, created = ShippingSettings.objects.get_or_create(
        pk=ShippingSettings.objects.first().pk if ShippingSettings.objects.exists() else None
    )
    return settings


def get_tax_settings():
    """Get or create tax settings (singleton per tenant)."""
    settings, created = TaxSettings.objects.get_or_create(
        pk=TaxSettings.objects.first().pk if TaxSettings.objects.exists() else None
    )
    return settings


def get_notification_settings():
    """Get or create notification settings (singleton per tenant)."""
    settings, created = NotificationSettings.objects.get_or_create(
        pk=NotificationSettings.objects.first().pk if NotificationSettings.objects.exists() else None
    )
    return settings


def get_policy_settings():
    """Get or create policy settings (singleton per tenant)."""
    settings, created = PolicySettings.objects.get_or_create(
        pk=PolicySettings.objects.first().pk if PolicySettings.objects.exists() else None
    )
    return settings


def get_checkout_settings():
    """Get or create checkout settings (singleton per tenant)."""
    settings, created = CheckoutSettings.objects.get_or_create(
        pk=CheckoutSettings.objects.first().pk if CheckoutSettings.objects.exists() else None
    )
    return settings


def get_security_settings():
    """Get or create security settings (singleton per tenant)."""
    settings, created = SecuritySettings.objects.get_or_create(
        pk=SecuritySettings.objects.first().pk if SecuritySettings.objects.exists() else None
    )
    return settings


def get_feature_settings():
    """Get or create feature settings (singleton per tenant)."""
    settings, created = FeatureSettings.objects.get_or_create(
        pk=FeatureSettings.objects.first().pk if FeatureSettings.objects.exists() else None
    )
    return settings


def get_all_settings():
    """Get all settings as a dictionary."""
    return {
        'general': get_general_settings(),
        'branding': get_branding_settings(),
        'seo': get_seo_settings(),
        'payment': get_payment_settings(),
        'shipping': get_shipping_settings(),
        'tax': get_tax_settings(),
        'notification': get_notification_settings(),
        'policy': get_policy_settings(),
        'checkout': get_checkout_settings(),
        'security': get_security_settings(),
        'feature': get_feature_settings(),
    }
