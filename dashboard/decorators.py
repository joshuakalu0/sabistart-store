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
    """
    @wraps(view_func)
    def wrapper(request, prefix, *args, **kwargs):
        return view_func(request, prefix, *args, **kwargs)

    return wrapper

