from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Q
from dashboard.decorators import dashboard_prefix_required

from ..models import NotificationPreference, NotificationBlacklist

@login_required
@dashboard_prefix_required
def preference_list(request, prefix):
    """List customer notification preferences."""
    search_query = request.GET.get('q', '')
    category_filter = request.GET.get('category_id')
    
    preferences = NotificationPreference.objects.select_related('customer', 'category').all()
    
    if search_query:
        preferences = preferences.filter(
            Q(customer__email__icontains=search_query) | 
            Q(customer__first_name__icontains=search_query) |
            Q(customer__last_name__icontains=search_query)
        )
        
    if category_filter:
        preferences = preferences.filter(category_id=category_filter)
        
    paginator = Paginator(preferences, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'preferences': page_obj,
        'page_title': 'Customer Preferences',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/preference/list.html', context)


@login_required
@dashboard_prefix_required
def blacklist_list(request, prefix):
    """List the global notification blacklist."""
    search_query = request.GET.get('q', '')
    type_filter = request.GET.get('type')
    
    blacklist = NotificationBlacklist.objects.all()
    
    if search_query:
        blacklist = blacklist.filter(value__icontains=search_query)
        
    if type_filter:
        blacklist = blacklist.filter(entry_type=type_filter)
        
    paginator = Paginator(blacklist, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'blacklist': page_obj,
        'page_title': 'Global Suppression List',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/blacklist/list.html', context)
