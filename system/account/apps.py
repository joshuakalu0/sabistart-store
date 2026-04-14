from django.apps import AppConfig


class AccountConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system.account'
    
    def ready(self):
        # Import signals to register them
        import system.account.signals