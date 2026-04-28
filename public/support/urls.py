from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    path('help/', views.help_center_view, name='help_center'),
    path('help/faq/<slug:faq_slug>/', views.faq_detail_view, name='faq_detail'),
    path('contact/', views.contact_us_view, name='contact_us'),
    path('tickets/submit/', views.submit_ticket_view, name='submit_ticket'),
    path('tickets/<uuid:ticket_id>/', views.ticket_status_view, name='ticket_status'),
    path('delivery/', views.delivery_info_view, name='delivery_info'),
    path('returns/', views.returns_policy_view, name='returns_policy'),
    path('warranty/', views.warranty_info_view, name='warranty_info'),
]
