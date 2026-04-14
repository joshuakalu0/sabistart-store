"""
Professional Settings Views
Clean, consistent view handlers with proper error handling
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from public.store_settings.models import StoreSettings
from .forms import (
    GeneralSettingsForm, BrandingSettingsForm, SEOSettingsForm,
    PaymentSettingsForm, ShippingSettingsForm, TaxSettingsForm,
    NotificationSettingsForm, PolicySettingsForm, CheckoutSettingsForm,
    SecuritySettingsForm, FeatureSettingsForm
)
from dashboard.sidebar_utiles import main_sidebar, get_settings_sidebar, get_sidebar_with_active, get_sub_sidebar_with_active


@login_required
@dashboard_prefix_required
def settings_index(request, prefix):
    """Settings dashboard with tab navigation."""

    # Get current settings
    settings = StoreSettings.objects.get_settings()

    context = {
        'prefix': '',
        'page_title': 'Business Setup',
        'active_menu': 'settings',
        'store_name': 'My Store',
        'settings': settings,
        'settings_categories': [
            {
                'name': 'General',
                'url': 'general',
                'icon': 'building',
                'description': 'Store identity and localization'
            },
            {
                'name': 'Website Setup',
                'url': 'branding',
                'icon': 'palette',
                'description': 'Visual identity and theme'
            },
            {
                'name': 'Vendors',
                'url': 'payment',
                'icon': 'users',
                'description': 'Payment gateways'
            },
            {
                'name': 'Products',
                'url': 'feature',
                'icon': 'package',
                'description': 'Product features'
            },
            {
                'name': 'Delivery Men',
                'url': 'shipping',
                'icon': 'truck',
                'description': 'Shipping settings'
            },
            {
                'name': 'Customer',
                'url': 'checkout',
                'icon': 'user',
                'description': 'Customer settings'
            },
            {
                'name': 'Orders',
                'url': 'notification',
                'icon': 'shopping-bag',
                'description': 'Order notifications'
            },
            {
                'name': 'Refund',
                'url': 'policy',
                'icon': 'rotate-ccw',
                'description': 'Refund policies'
            },
            {
                'name': 'Shipping Method',
                'url': 'shipping',
                'icon': 'map',
                'description': 'Shipping methods'
            },
            {
                'name': 'Delivery Zone',
                'url': 'tax',
                'icon': 'map-pin',
                'description': 'Tax zones'
            },
            {
                'name': 'SEO',
                'url': 'seo',
                'icon': 'search',
                'description': 'SEO settings'
            },
            {
                'name': 'Security',
                'url': 'security',
                'icon': 'shield',
                'description': 'Security settings'
            },
        ]
    }
    return render(request, 'dashboard/settings/index.html', context)


def handle_settings_form(request, prefix, form_class, url_name, page_title, page_description, template_name, sidebar=None, sub_sidebar=None):
    """
    Generic handler for settings forms.

    Args:
        request: HTTP request
        form_class: Form class to use
        url_name: URL name for redirect
        page_title: Page title
        page_description: Page description
        template_name: Template name for rendering
        sub_sidebar: Sub sidebar for settings

    Returns:
        HttpResponse
    """
    # Get singleton settings instance
    settings = StoreSettings.objects.get_settings()

    if request.method == 'POST':
        form = form_class(request.POST, request.FILES, instance=settings)

        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()

                messages.success(
                    request, f'{page_title} updated successfully!')

                # Return JSON for AJAX requests
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f'{page_title} updated successfully!'
                    })

                return redirect(reverse(f'dashboard:dashboard_settings:{url_name}', kwargs={'prefix': prefix}))

            except Exception as e:
                messages.error(request, f'Error saving settings: {str(e)}')

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': f'Error saving settings: {str(e)}'
                    }, status=400)
        else:
            messages.error(request, 'Please correct the errors below.')

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
    else:
        form = form_class(instance=settings)

    context = {
        'prefix': prefix,
        'form': form,
        'settings': settings,
        'page_title': page_title,
        'page_description': page_description,
        'url_name': url_name,
        'active_menu': 'settings',
        'store_name': 'My Store',
        'sidebar':  sidebar if sidebar else main_sidebar(prefix),
        'sub_sidebar': sub_sidebar if sub_sidebar else None,
    }

    return render(request, template_name, context)


@login_required
@dashboard_prefix_required
def general_settings(request, prefix):
    """General settings page."""
    # Get singleton settings instance
    return handle_settings_form(
        request,
        prefix,
        GeneralSettingsForm,
        'general',
        'General Settings',
        'General settings',
        'dashboard/settings/general.html',
        sidebar=get_sidebar_with_active('business setup', prefix),
        sub_sidebar=get_sub_sidebar_with_active('general', prefix)
    )


@login_required
@dashboard_prefix_required
def branding_settings(request, prefix):
    """Branding settings page."""
    # Get singleton settings instance
    return handle_settings_form(
        request,
        prefix,
        BrandingSettingsForm,
        'branding',
        'Branding Settings',
        'Branding settings',
        'dashboard/settings/branding.html',
        sidebar=get_sidebar_with_active('business setup', prefix),
        sub_sidebar=get_sub_sidebar_with_active('branding', prefix)
    )


@login_required
@dashboard_prefix_required
def seo_settings(request, prefix):
    """SEO settings page."""
    return handle_settings_form(
        request,
        prefix,
        SEOSettingsForm,
        'seo',
        'SEO Settings',
        'SEO settings',
        'dashboard/settings/seo.html',
        sidebar=get_sidebar_with_active('business setup', prefix),
        sub_sidebar=get_sub_sidebar_with_active('seo', prefix)
    )


@login_required
@dashboard_prefix_required
def payment_settings(request, prefix):
    """Payment settings page."""
    return handle_settings_form(
        request,
        prefix,
        PaymentSettingsForm,
        'payment',
        'Payment Settings',
        'Configure payment gateways and transaction methods'
    )


@login_required
@dashboard_prefix_required
def shipping_settings(request, prefix):
    """Shipping settings page."""
    return handle_settings_form(
        request,
        prefix,
        ShippingSettingsForm,
        'shipping',
        'Shipping Settings',
        'Manage shipping rates, zones, and delivery options'
    )


@login_required
@dashboard_prefix_required
def tax_settings(request, prefix):
    """Tax settings page."""
    return handle_settings_form(
        request,
        prefix,
        TaxSettingsForm,
        'tax',
        'Tax Settings',
        'Configure tax rules, rates, and compliance settings'
    )


@login_required
@dashboard_prefix_required
def notification_settings(request, prefix):
    """Notification settings page."""
    return handle_settings_form(
        request,
        prefix,
        NotificationSettingsForm,
        'notification',
        'Notification Settings',
        'Manage email, SMS, and alert notifications'
    )


@login_required
@dashboard_prefix_required
def policy_settings(request, prefix):
    """Policy settings page."""
    return handle_settings_form(
        request,
        prefix,
        PolicySettingsForm,
        'policy',
        'Policy Settings',
        'Configure legal policies and terms of service'
    )


@login_required
@dashboard_prefix_required
def checkout_settings(request, prefix):
    """Checkout settings page."""
    return handle_settings_form(
        request,
        prefix,
        CheckoutSettingsForm,
        'checkout',
        'Checkout Settings',
        'Customize cart and checkout experience'
    )


@login_required
@dashboard_prefix_required
def security_settings(request, prefix):
    """Security settings page."""
    return handle_settings_form(
        request,
        prefix,
        SecuritySettingsForm,
        'security',
        'Security Settings',
        'Configure access control and security policies'
    )


@login_required
@dashboard_prefix_required
def feature_settings(request, prefix):
    """Feature settings page."""
    return handle_settings_form(
        request,
        prefix,
        FeatureSettingsForm,
        'feature',
        'Feature Settings',
        'Enable or disable store features and integrations'
    )


@login_required
@require_http_methods(["POST"])
def toggle_maintenance_mode(request):
    """AJAX endpoint to toggle maintenance mode."""
    settings = StoreSettings.objects.get_settings()
    settings.maintenance_mode = not settings.maintenance_mode
    settings.save()

    return JsonResponse({
        'success': True,
        'maintenance_mode': settings.maintenance_mode,
        'message': f"Maintenance mode {'enabled' if settings.maintenance_mode else 'disabled'}"
    })
