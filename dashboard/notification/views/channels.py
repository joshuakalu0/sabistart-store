from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from dashboard.decorators import dashboard_prefix_required

from ..models import (
    NotificationChannel, EmailChannelConfig, SMSChannelConfig,
    PushChannelConfig, SlackChannelConfig, ChannelType
)
from ..forms import (
    NotificationChannelForm, EmailChannelConfigForm, SMSChannelConfigForm,
    PushChannelConfigForm, SlackChannelConfigForm
)

@login_required
@dashboard_prefix_required
def channel_list(request, prefix):
    """List all notification channels."""
    channels = NotificationChannel.objects.select_related('created_by').order_by('channel_type', '-is_default', 'name')
    
    context = {
        'channels': channels,
        'page_title': 'Notification Channels',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/channel/list.html', context)


@login_required
@dashboard_prefix_required
def channel_detail(request, prefix, pk):
    """View details of a specific notification channel."""
    channel = get_object_or_404(NotificationChannel, pk=pk)
    
    config = None
    if channel.channel_type == ChannelType.EMAIL and hasattr(channel, 'email_config'):
        config = channel.email_config
    elif channel.channel_type == ChannelType.SMS and hasattr(channel, 'sms_config'):
        config = channel.sms_config
    elif channel.channel_type == ChannelType.PUSH and hasattr(channel, 'push_config'):
        config = channel.push_config
    elif channel.channel_type == ChannelType.SLACK and hasattr(channel, 'slack_config'):
        config = channel.slack_config
        
    recent_jobs = channel.jobs.order_by('-created_at')[:10]
    recent_logs = channel.logs.order_by('-created_at')[:10]

    context = {
        'channel': channel,
        'config': config,
        'recent_jobs': recent_jobs,
        'recent_logs': recent_logs,
        'page_title': f'Channel: {channel.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/channel/detail.html', context)


@login_required
@dashboard_prefix_required
def channel_create(request, prefix):
    """Create a new notification channel and its specific configuration."""
    if request.method == 'POST':
        form = NotificationChannelForm(request.POST)
        if form.is_valid():
            channel = form.save(commit=False)
            channel.created_by = request.user
            channel.save()
            
            # Automatically create a blank config based on type
            if channel.channel_type == ChannelType.EMAIL:
                EmailChannelConfig.objects.create(channel=channel)
            elif channel.channel_type == ChannelType.SMS:
                SMSChannelConfig.objects.create(channel=channel)
            elif channel.channel_type == ChannelType.PUSH:
                PushChannelConfig.objects.create(channel=channel)
            elif channel.channel_type == ChannelType.SLACK:
                SlackChannelConfig.objects.create(channel=channel)
                
            messages.success(request, f"Channel '{channel.name}' created successfully. Please configure it now.")
            return redirect('notification_channel_update', prefix=prefix, pk=channel.pk)
    else:
        form = NotificationChannelForm()

    context = {
        'form': form,
        'is_new': True,
        'page_title': 'Create Notification Channel',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/channel/form.html', context)


@login_required
@dashboard_prefix_required
def channel_update(request, prefix, pk):
    """Update a channel and its provider-specific configuration."""
    channel = get_object_or_404(NotificationChannel, pk=pk)
    
    config_instance = None
    ConfigFormClass = None
    
    if channel.channel_type == ChannelType.EMAIL:
        config_instance = getattr(channel, 'email_config', None)
        ConfigFormClass = EmailChannelConfigForm
        if not config_instance:
            config_instance = EmailChannelConfig.objects.create(channel=channel)
    elif channel.channel_type == ChannelType.SMS:
        config_instance = getattr(channel, 'sms_config', None)
        ConfigFormClass = SMSChannelConfigForm
        if not config_instance:
            config_instance = SMSChannelConfig.objects.create(channel=channel)
    elif channel.channel_type == ChannelType.PUSH:
        config_instance = getattr(channel, 'push_config', None)
        ConfigFormClass = PushChannelConfigForm
        if not config_instance:
            config_instance = PushChannelConfig.objects.create(channel=channel)
    elif channel.channel_type == ChannelType.SLACK:
        config_instance = getattr(channel, 'slack_config', None)
        ConfigFormClass = SlackChannelConfigForm
        if not config_instance:
            config_instance = SlackChannelConfig.objects.create(channel=channel)

    if request.method == 'POST':
        form = NotificationChannelForm(request.POST, instance=channel)
        
        config_form = None
        if ConfigFormClass:
            config_form = ConfigFormClass(request.POST, instance=config_instance)
            
        is_config_valid = config_form.is_valid() if config_form else True
            
        if form.is_valid() and is_config_valid:
            form.save()
            if config_form:
                config_form.save()
            messages.success(request, f"Channel '{channel.name}' updated successfully.")
            return redirect('notification_channel_detail', prefix=prefix, pk=channel.pk)
    else:
        form = NotificationChannelForm(instance=channel)
        config_form = ConfigFormClass(instance=config_instance) if ConfigFormClass else None

    context = {
        'form': form,
        'config_form': config_form,
        'channel': channel,
        'is_new': False,
        'page_title': f'Edit Channel: {channel.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/channel/form.html', context)


@login_required
@dashboard_prefix_required
def channel_delete(request, prefix, pk):
    """Delete a channel. Handles confirmation and execution."""
    channel = get_object_or_404(NotificationChannel, pk=pk)
    
    if request.method == 'POST':
        name = channel.name
        channel.delete()
        messages.success(request, f"Channel '{name}' deleted successfully.")
        return redirect('notification_channel_list', prefix=prefix)
        
    context = {
        'channel': channel,
        'page_title': f'Delete Channel: {channel.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/channel/delete.html', context)
