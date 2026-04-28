import logging
from django.db.models.signals import post_migrate, post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)


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
        
        # Import models here to avoid circular imports
        from .store_settings import StoreSettings
        from .theme_settings import ThemeSettings
        from .header_settings import HeaderSettings
        from .footer_settings import FooterSettings
        from .homepage_layout import HomepageLayout
        from .product_display_settings import ProductDisplaySettings
        from .product_page_settings import ProductPageSettings
        from .cart_settings import CartSettings
        from .checkout_settings import CheckoutSettings
        from .search_settings import SearchSettings
        from .email_template_settings import EmailTemplateSettings
        from .social_media_links import SocialMediaLinks
        from .notification_settings import NotificationSettings
        from .mobile_app_settings import MobileAppSettings
        from .blog_settings import BlogSettings
        from .popup_settings import PopupSettings
        from .performance_settings import PerformanceSettings
        from .navigation import NavigationMenu
        
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
@receiver(post_save)
def invalidate_settings_cache(sender, instance, **kwargs):
    """Invalidate cache when settings are updated."""
    # Only invalidate for settings models
    if sender.__name__.endswith('Settings'):
        cache_key = f'store_settings_{connection.schema_name}'
        cache.delete(cache_key)
        logger.debug(f"Cache invalidated for {sender.__name__}")


@receiver(post_delete)
def invalidate_settings_cache_on_delete(sender, instance, **kwargs):
    """Invalidate cache when settings are deleted."""
    # Only invalidate for settings models
    if sender.__name__.endswith('Settings'):
        cache_key = f'store_settings_{connection.schema_name}'
        cache.delete(cache_key)
        logger.debug(f"Cache invalidated on delete for {sender.__name__}")
