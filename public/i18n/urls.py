from django.urls import path
from . import views

app_name = 'i18n'

urlpatterns = [
    path('region-select/', views.region_selector_view, name='region_selector'),
    path('geo-redirect/', views.geo_redirect_view, name='geo_redirect'),
    path('set-language/', views.set_language_view, name='set_language'),
]
