from django.urls import path

from dashboard.domain import views


app_name = "domain"


urlpatterns = [
    path("", views.domain_list, name="list"),
    path("add/", views.domain_add, name="add"),
    path("<uuid:domain_id>/", views.domain_detail, name="detail"),
    path("<uuid:domain_id>/delete/", views.domain_delete, name="delete"),
    path("<uuid:domain_id>/set-primary/", views.domain_set_primary, name="set_primary"),
    path("<uuid:domain_id>/verify/", views.domain_retrigger_verification, name="verify"),
    path("<uuid:domain_id>/status/", views.domain_status_partial, name="status"),
]
