from functools import wraps
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.db import connection
from django.db.utils import ProgrammingError
# from django.conf import settings


def dashboard_prefix_required(view_func):
    """
    Decorator to validate dashboard prefix from URL.

    Usage:
        @dashboard_prefix_required
        def my_dashboard_view(request, prefix):
            ...

    Security:
    - Validates prefix against database
    - Returns 404 if prefix doesn't match
    - Prevents unauthorized dashboard access
    """
    @wraps(view_func)
    def wrapper(request, prefix, *args, **kwargs):

        # prefix = 'admin'
        try:
            from public.store_settings.models import StoreSettings

            settings = StoreSettings.objects.get_settings()
            # print(settings)

            # Validate prefix matches stored value
            # print(prefix, '=============', settings.dashboard_path_prefix)
            if prefix != settings.dashboard_path_prefix:
                raise Http404("Invalid dashboard URL")

            # Attach settings to request for easy access in views
            # request.dashboard_settings = settings
            # print('working')

            return view_func(request, prefix, *args, **kwargs)

        except ProgrammingError as e:
            print(e,'======')
            # Table doesn't exist - migrations not run
            raise Http404("Dashboard not configured. Run migrations.")
        except Exception as e:
            print(e,'+++++')
            raise Http404("Dashboard not configured")

    return wrapper
