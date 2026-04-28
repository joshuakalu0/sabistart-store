from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from dashboard.decorators import dashboard_prefix_required

from ..models import (
    NotificationCategory, NotificationTemplate, NotificationTemplateVersion
)
from ..forms import (
    NotificationCategoryForm, NotificationTemplateForm, NotificationTemplateVersionForm
)

# --- Category Views ---

@login_required
@dashboard_prefix_required
def category_list(request, prefix):
    categories = NotificationCategory.objects.all()
    context = {
        'categories': categories,
        'page_title': 'Notification Categories',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/category/list.html', context)

@login_required
@dashboard_prefix_required
def category_create(request, prefix):
    if request.method == 'POST':
        form = NotificationCategoryForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Category '{cat.name}' created.")
            return redirect('notification_category_list', prefix=prefix)
    else:
        form = NotificationCategoryForm()
        
    context = {
        'form': form,
        'is_new': True,
        'page_title': 'Create Category',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/category/form.html', context)

@login_required
@dashboard_prefix_required
def category_update(request, prefix, pk):
    category = get_object_or_404(NotificationCategory, pk=pk)
    if request.method == 'POST':
        form = NotificationCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{category.name}' updated.")
            return redirect('notification_category_list', prefix=prefix)
    else:
        form = NotificationCategoryForm(instance=category)
        
    context = {
        'form': form,
        'category': category,
        'is_new': False,
        'page_title': f'Edit Category: {category.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/category/form.html', context)


# --- Template Views ---

@login_required
@dashboard_prefix_required
def template_list(request, prefix):
    templates = NotificationTemplate.objects.select_related('category', 'channel', 'active_version').all()
    
    status_filter = request.GET.get('status')
    if status_filter:
        templates = templates.filter(status=status_filter)
        
    channel_filter = request.GET.get('channel_type')
    if channel_filter:
        templates = templates.filter(channel_type=channel_filter)
        
    paginator = Paginator(templates, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'templates': page_obj,
        'page_title': 'Notification Templates',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/template/list.html', context)

@login_required
@dashboard_prefix_required
def template_create(request, prefix):
    if request.method == 'POST':
        form = NotificationTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.created_by = request.user
            template.last_modified_by = request.user
            template.save()
            messages.success(request, f"Template '{template.name}' created. You can now add a version.")
            return redirect('notification_template_version_create', prefix=prefix, template_pk=template.pk)
    else:
        form = NotificationTemplateForm()
        
    context = {
        'form': form,
        'is_new': True,
        'page_title': 'Create Template',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/template/form.html', context)

@login_required
@dashboard_prefix_required
def template_update(request, prefix, pk):
    template = get_object_or_404(NotificationTemplate, pk=pk)
    if request.method == 'POST':
        form = NotificationTemplateForm(request.POST, instance=template)
        if form.is_valid():
            t = form.save(commit=False)
            t.last_modified_by = request.user
            t.save()
            messages.success(request, f"Template '{template.name}' updated.")
            return redirect('notification_template_list', prefix=prefix)
    else:
        form = NotificationTemplateForm(instance=template)
        
    context = {
        'form': form,
        'template': template,
        'is_new': False,
        'page_title': f'Edit Template: {template.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/template/form.html', context)

@login_required
@dashboard_prefix_required
def template_version_history(request, prefix, template_pk):
    template = get_object_or_404(NotificationTemplate, pk=template_pk)
    versions = template.versions.all().order_by('-version_number')
    
    context = {
        'template': template,
        'versions': versions,
        'page_title': f'Version History: {template.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/template/version_history.html', context)

@login_required
@dashboard_prefix_required
def template_version_create(request, prefix, template_pk):
    template = get_object_or_404(NotificationTemplate, pk=template_pk)
    if request.method == 'POST':
        form = NotificationTemplateVersionForm(request.POST)
        if form.is_valid():
            version = form.save(commit=False)
            version.template = template
            version.created_by = request.user
            version.save()
            
            # Optionally activate if it's the first version
            if template.versions.count() == 1:
                version.activate(actor=request.user)
                messages.success(request, f"Version 1 created and activated automatically.")
            else:
                messages.success(request, f"Version {version.version_number} created as draft.")
                
            return redirect('notification_template_version_history', prefix=prefix, template_pk=template.pk)
    else:
        # Pre-fill form from the active version if it exists
        initial = {}
        if template.active_version:
            av = template.active_version
            initial = {
                'subject': av.subject,
                'preheader': av.preheader,
                'html_body': av.html_body,
                'text_body': av.text_body,
                'title': av.title,
                'body': av.body,
                'action_url': av.action_url,
                'action_label': av.action_label,
            }
        form = NotificationTemplateVersionForm(initial=initial)
        
    context = {
        'form': form,
        'template': template,
        'page_title': f'Create Version for {template.name}',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/template/version_form.html', context)

@login_required
@dashboard_prefix_required
def template_version_activate(request, prefix, pk):
    version = get_object_or_404(NotificationTemplateVersion, pk=pk)
    if request.method == 'POST':
        version.activate(actor=request.user)
        messages.success(request, f"Version {version.version_number} is now active.")
    return redirect('notification_template_version_history', prefix=prefix, template_pk=version.template_id)
