from django.apps import AppConfig


class DomainsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard.domain"
    verbose_name = "Custom Domain Management"

    def ready(self):
        import dashboard.domain.signals  # noqa: F401
