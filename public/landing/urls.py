from django.urls import path
from . import views

app_name = 'landing'

urlpatterns = [
    path('', views.landing_home, name='home'),
    path('about/', views.landing_about, name='about'),
    path('features/', views.landing_features, name='features'),
    path('pricing/', views.landing_pricing, name='pricing'),
    path('contact/', views.landing_contact, name='contact'),
]
