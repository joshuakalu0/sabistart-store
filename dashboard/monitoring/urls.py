from django.urls import path

from dashboard.monitoring import views


app_name = "monitoring"


urlpatterns = [
    path("", views.overview, name="overview"),
    path("pages/", views.pages, name="pages"),
    path("sessions/", views.sessions, name="sessions"),
]

