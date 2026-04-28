"""
Middleware for tracking current user in thread-local storage.
"""
from django.utils.deprecation import MiddlewareMixin
from dashboard.settings.models import set_current_user


class CurrentUserMiddleware(MiddlewareMixin):
    """
    Middleware that stores the current authenticated user in thread-local storage
    for access in models and other places without passing the request object.
    """

    def process_request(self, request):
        """Set current user when request starts."""
        if hasattr(request, 'user') and request.user.is_authenticated:
            set_current_user(request.user)
        else:
            set_current_user(None)

    def process_response(self, request, response):
        """Clean up thread-local storage when response is sent."""
        set_current_user(None)
        return response

    def process_exception(self, request, exception):
        """Clean up thread-local storage if an exception occurs."""
        set_current_user(None)
