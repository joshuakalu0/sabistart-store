from django.apps import AppConfig


class UserauthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'public.userauth'
    
    def ready(self):
        # Import signals to register them
        import public.userauth.signals