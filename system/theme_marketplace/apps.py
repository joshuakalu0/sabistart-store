from django.apps import AppConfig


class ThemeMarketplaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "system.theme_marketplace"
    verbose_name = "Theme Marketplace"

    def ready(self):
        from system.theme_marketplace import signals  # noqa: F401
