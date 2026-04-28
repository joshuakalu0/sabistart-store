from django.urls import path

from public.monitoring import views


app_name = "monitoring"


urlpatterns = [
    path("beacon/", views.beacon, name="beacon"),
]
