from django.urls import path

from dashboard.feature_marketplace import views


app_name = "feature_marketplace"


urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("features/<slug:code>/", views.feature_detail, name="feature_detail"),
    path("bundles/<slug:slug>/", views.bundle_detail, name="bundle_detail"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/direct/", views.checkout_direct, name="checkout_direct"),
    path("checkout/preview/", views.preview_api, name="preview_api"),
    path("purchases/", views.purchases, name="purchases"),
    path("purchases/<str:purchase_reference>/success/", views.purchase_success, name="purchase_success"),
    path("purchases/<str:purchase_reference>/cancel/", views.purchase_cancel, name="purchase_cancel"),
    path("entitlements/", views.entitlements, name="entitlements"),
    path("usage/", views.usage, name="usage"),
]
