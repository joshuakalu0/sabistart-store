from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from dashboard.decorators import dashboard_prefix_required


@login_required
@dashboard_prefix_required
def dashboard_home(request, prefix):
    """Dashboard home page - requires valid prefix."""
    context = {
        'prefix': prefix,
        'page_title': 'Dashboard',
        'active_menu': 'home',
        'store_name': 'My Store'
    }
    return render(request, 'dashboard/home/index.html', context)
