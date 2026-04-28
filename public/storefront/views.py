from django.http import HttpResponse
from django.urls import reverse

from public.category.views import catalog_view
from public.home.views import home_view
from public.product.views import product_detail_view


def home(request):
    """Legacy storefront entrypoint routed to the tenant-aware home view."""
    return home_view(request)


def product_list(request):
    """Legacy storefront catalog entrypoint routed to the live catalog view."""
    return catalog_view(request)


def product_detail(request, slug):
    """Legacy product detail entrypoint routed to the live product page."""
    return product_detail_view(request, product_slug=slug)


def test_tenant_urls(request):
    """Basic URL smoke view for tenant account routes."""
    return HttpResponse(
        f"""
        Tenant URL test:<br>
        Register: <a href="{reverse('tenant:register')}">{reverse('tenant:register')}</a><br>
        Login: <a href="{reverse('tenant:login')}">{reverse('tenant:login')}</a><br>
        Logout: <a href="{reverse('tenant:logout')}">{reverse('tenant:logout')}</a><br>
        Account: <a href="{reverse('tenant:account_overview')}">{reverse('tenant:account_overview')}</a>
        """
    )
