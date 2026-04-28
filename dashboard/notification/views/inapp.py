from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from dashboard.decorators import dashboard_prefix_required

from ..models import InAppNotification
from ..forms import InAppNotificationForm

@login_required
@dashboard_prefix_required
def inapp_list(request, prefix):
    """List in-app notifications targeting staff or customers."""
    audience_filter = request.GET.get('audience')
    
    notifications = InAppNotification.objects.select_related('created_by').all()
    if audience_filter:
        notifications = notifications.filter(audience=audience_filter)
        
    paginator = Paginator(notifications, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'notifications': page_obj,
        'page_title': 'In-App Notifications',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/inapp/list.html', context)


@login_required
@dashboard_prefix_required
def inapp_create(request, prefix):
    """Create a new in-app notification to broadcast to the dashboard or customer portal."""
    if request.method == 'POST':
        form = InAppNotificationForm(request.POST)
        if form.is_valid():
            noti = form.save(commit=False)
            noti.created_by = request.user
            noti.save()
            messages.success(request, f"In-App Notification '{noti.title}' created.")
            return redirect('notification_inapp_list', prefix=prefix)
    else:
        form = InAppNotificationForm()
        
    context = {
        'form': form,
        'is_new': True,
        'page_title': 'Create In-App Notification',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/inapp/form.html', context)


@login_required
@dashboard_prefix_required
def inapp_update(request, prefix, pk):
    noti = get_object_or_404(InAppNotification, pk=pk)
    if request.method == 'POST':
        form = InAppNotificationForm(request.POST, instance=noti)
        if form.is_valid():
            form.save()
            messages.success(request, f"In-App Notification '{noti.title}' updated.")
            return redirect('notification_inapp_list', prefix=prefix)
    else:
        form = InAppNotificationForm(instance=noti)
        
    context = {
        'form': form,
        'noti': noti,
        'is_new': False,
        'page_title': f'Edit In-App Notification: {noti.title}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/inapp/form.html', context)
