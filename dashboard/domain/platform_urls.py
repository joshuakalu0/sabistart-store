from django.urls import path

from dashboard.domain import platform_views


app_name = "platform_domains"


urlpatterns = [
    path("", platform_views.home, name="home"),
    path("providers/", platform_views.providers, name="providers"),
    path("providers/credentials/new/", platform_views.provider_credential_create, name="provider_credential_create"),
    path("providers/credentials/<uuid:credential_id>/edit/", platform_views.provider_credential_edit, name="provider_credential_edit"),
    path("tlds/", platform_views.tlds, name="tlds"),
    path("orders/", platform_views.orders, name="orders"),
    path("managed/", platform_views.managed_domains, name="managed_domains"),
    path("renewals/", platform_views.renewals, name="renewals"),
    path("checkout/<str:purchase_reference>/", platform_views.checkout_session, name="checkout_session"),
    path("callback/<str:purchase_reference>/", platform_views.payment_callback, name="payment_callback"),
    path("webhooks/<str:provider>/", platform_views.payment_webhook, name="payment_webhook"),
]
