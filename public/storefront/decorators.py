from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.views.decorators.cache import cache_page
from .utils import get_site_settings

def b2b_required(view_func):
    """Redirects non-B2B users if B2B is enforced."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        settings = get_site_settings(request)
        if settings['features'].get('enable_b2b') and not getattr(request.user, 'is_b2b', False):
            messages.error(request, "This area is restricted to B2B customers only.")
            return redirect('tenant:login') # Replace with actual login URL name
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def cache_response(timeout=60 * 15):
    """Wrapper around cache_page for consistent usage."""
    return cache_page(timeout)
