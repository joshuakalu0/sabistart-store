from django.urls import path
from . import views

app_name = 'home'

urlpatterns = [
    path('', views.home_view, name='index'),
    path('maintenance/', views.maintenance_view, name='maintenance'),
    path('coming-soon/', views.coming_soon_view, name='coming_soon'),
]
