from django.urls import path
from . import views

app_name = 'legal'

urlpatterns = [
    path('terms/', views.terms_of_service_view, name='terms_of_service'),
    path('privacy/', views.privacy_policy_view, name='privacy_policy'),
    path('cookies/', views.cookie_policy_view, name='cookie_policy'),
    path('dmca/', views.dmca_policy_view, name='dmca_policy'),
    path('accessibility/', views.accessibility_statement_view, name='accessibility'),
    path('slavery/', views.modern_slavery_statement_view, name='slavery_statement'),
    path('compliance/', views.compliance_view, name='compliance'),
    path('cookie-preferences/', views.cookie_preferences_view, name='cookie_preferences'),
]
