from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from dashboard.decorators import dashboard_prefix_required

from ..models import NotificationJob, NotificationLog, NotificationEvent, BounceRecord

@login_required
@dashboard_prefix_required
def job_list(request, prefix):
    """List scheduled or processing notification jobs."""
    status_filter = request.GET.get('status')
    
    jobs = NotificationJob.objects.select_related('template', 'channel').all()
    if status_filter:
        jobs = jobs.filter(status=status_filter)
        
    paginator = Paginator(jobs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'jobs': page_obj,
        'page_title': 'Notification Jobs Queue',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/delivery/job_list.html', context)


@login_required
@dashboard_prefix_required
def log_list(request, prefix):
    """List immutable delivery logs."""
    status_filter = request.GET.get('status')
    search_query = request.GET.get('q', '')
    
    logs = NotificationLog.objects.select_related('template', 'channel').all()
    
    if status_filter:
        logs = logs.filter(status=status_filter)
        
    if search_query:
        logs = logs.filter(
            Q(recipient_address__icontains=search_query) |
            Q(provider_message_id__icontains=search_query)
        )
        
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'logs': page_obj,
        'page_title': 'Delivery Logs',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/delivery/log_list.html', context)


@login_required
@dashboard_prefix_required
def log_detail(request, prefix, pk):
    """View details of a specific delivery log, including the event timeline."""
    log = get_object_or_404(NotificationLog.objects.select_related('template', 'channel', 'job'), pk=pk)
    events = log.events.order_by('-created_at')
    bounces = getattr(log, 'bounces', None)
    if bounces:
        bounces = bounces.all()
    
    context = {
        'log': log,
        'events': events,
        'bounces': bounces,
        'page_title': f'Delivery Log Details',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/delivery/log_detail.html', context)


@login_required
@dashboard_prefix_required
def bounce_list(request, prefix):
    """List email hard and soft bounces."""
    type_filter = request.GET.get('type')
    search_query = request.GET.get('q', '')
    
    bounces = BounceRecord.objects.all()
    
    if type_filter:
        bounces = bounces.filter(bounce_type=type_filter)
        
    if search_query:
        bounces = bounces.filter(email_address__icontains=search_query)
        
    paginator = Paginator(bounces, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'bounces': page_obj,
        'page_title': 'Bounce Records',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/delivery/bounce_list.html', context)
