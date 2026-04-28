from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import require_feature

from ..models import WebhookEndpoint, WebhookDeliveryAttempt, WebhookSigningSecret
from ..forms import WebhookEndpointForm

@login_required
@dashboard_prefix_required
@require_feature("webhooks")
def webhook_list(request, prefix):
    endpoints = WebhookEndpoint.objects.all()
    context = {
        'endpoints': endpoints,
        'page_title': 'Webhook Endpoints',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/webhook/list.html', context)

@login_required
@dashboard_prefix_required
@require_feature("webhooks")
def webhook_create(request, prefix):
    if request.method == 'POST':
        form = WebhookEndpointForm(request.POST)
        if form.is_valid():
            endpoint = form.save()
            endpoint.created_by = request.user
            endpoint.save()
            
            WebhookSigningSecret.generate(endpoint, created_by=request.user)
            messages.success(request, f"Webhook endpoint '{endpoint.name}' created along with its signing secret.")
            return redirect('notification_webhook_detail', prefix=prefix, pk=endpoint.pk)
    else:
        form = WebhookEndpointForm()
        
    context = {
        'form': form,
        'is_new': True,
        'page_title': 'Register Webhook Endpoint',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/webhook/form.html', context)

@login_required
@dashboard_prefix_required
@require_feature("webhooks")
def webhook_update(request, prefix, pk):
    endpoint = get_object_or_404(WebhookEndpoint, pk=pk)
    if request.method == 'POST':
        form = WebhookEndpointForm(request.POST, instance=endpoint)
        if form.is_valid():
            form.save()
            messages.success(request, f"Webhook endpoint '{endpoint.name}' updated.")
            return redirect('notification_webhook_detail', prefix=prefix, pk=endpoint.pk)
    else:
        form = WebhookEndpointForm(instance=endpoint)
        
    context = {
        'form': form,
        'endpoint': endpoint,
        'is_new': False,
        'page_title': f'Edit Webhook: {endpoint.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/webhook/form.html', context)

@login_required
@dashboard_prefix_required
@require_feature("webhooks")
def webhook_detail(request, prefix, pk):
    endpoint = get_object_or_404(WebhookEndpoint, pk=pk)
    subscriptions = endpoint.subscriptions.all()
    secrets = endpoint.signing_secrets.all().order_by('-created_at')
    
    recent_attempts = endpoint.delivery_attempts.order_by('-created_at')[:20]
    
    context = {
        'endpoint': endpoint,
        'subscriptions': subscriptions,
        'secrets': secrets,
        'recent_attempts': recent_attempts,
        'page_title': f'Webhook: {endpoint.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/webhook/detail.html', context)

@login_required
@dashboard_prefix_required
@require_feature("webhooks")
def webhook_delivery_logs(request, prefix, pk):
    endpoint = get_object_or_404(WebhookEndpoint, pk=pk)
    attempts = endpoint.delivery_attempts.order_by('-created_at')
    
    paginator = Paginator(attempts, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'endpoint': endpoint,
        'attempts': page_obj,
        'page_title': f'Delivery History: {endpoint.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/webhook/delivery_log.html', context)
