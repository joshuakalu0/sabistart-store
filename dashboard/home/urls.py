from django.urls import path
from dashboard.home import views

app_name = 'dashboard_home'

urlpatterns = [
    path('', views.dashboard_home, name='home'),
]
