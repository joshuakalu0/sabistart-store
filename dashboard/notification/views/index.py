from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from dashboard.decorators import dashboard_prefix_required

# Note: In a real system, you'd pull these from notifications.utils.dashboard
# We will mock the context lightly or import if available.
try:
    from notification.utiles.dashboard import (
        get_notifications_dashboard_kpis,
        get_channel_status_overview,
        get_recent_delivery_activity,
        get_notifications_health_checks
    )
    HAS_UTILS = True
except ImportError:
    HAS_UTILS = False

@login_required
@dashboard_prefix_required
def notification_dashboard_index(request, prefix):
    """
    Main landing page for the Notification Administration Dashboard.
    Displays KPIs, channel health, and recent delivery failures.
    """
    
    if HAS_UTILS:
        kpis = get_notifications_dashboard_kpis()
        health = get_notifications_health_checks()
        channel_status = get_channel_status_overview()
        recent_activity = get_recent_delivery_activity(limit=10)
    else:
        kpis = {}
        health = []
        channel_status = []
        recent_activity = []

    context = {
        'kpis': kpis,
        'health_checks': health,
        'channel_status': channel_status,
        'recent_activity': recent_activity,
        'page_title': 'Notification Dashboard',
        'prefix': prefix,
    }
    return render(request, 'dashboard/notification/index.html', context)
