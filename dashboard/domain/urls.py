from django.urls import path

from dashboard.domain import views


app_name = "domain"


urlpatterns = [
    path("", views.domain_list, name="list"),
    path("add/", views.domain_add, name="add"),
    path("buy/", views.domain_checkout, name="checkout"),
    path("portfolio/", views.domain_portfolio, name="portfolio"),
    path("orders/", views.domain_orders, name="orders"),
    path("orders/<str:purchase_reference>/", views.domain_order_detail, name="order_detail"),
    path("contacts/", views.domain_contacts, name="contacts"),
    path("notifications/", views.domain_notifications, name="notifications"),
    path("notifications/<uuid:notification_id>/read/", views.domain_notification_read, name="notification_read"),
    path("managed/<uuid:managed_domain_id>/", views.managed_domain_detail, name="managed_detail"),
    path("managed/<uuid:managed_domain_id>/connect/", views.managed_domain_connect, name="managed_connect"),
    path("managed/<uuid:managed_domain_id>/dns/", views.managed_domain_dns, name="managed_dns"),
    path("managed/<uuid:managed_domain_id>/renew/", views.managed_domain_renew, name="managed_renew"),
    path("<uuid:domain_id>/", views.domain_detail, name="detail"),
    path("<uuid:domain_id>/delete/", views.domain_delete, name="delete"),
    path("<uuid:domain_id>/set-primary/", views.domain_set_primary, name="set_primary"),
    path("<uuid:domain_id>/verify/", views.domain_retrigger_verification, name="verify"),
    path("<uuid:domain_id>/status/", views.domain_status_partial, name="status"),
]
