from django.apps import AppConfig


class PaymentsTenantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard.payments_tenant"
    label = "payments_tenant"
    verbose_name = "Dashboard Payments"
