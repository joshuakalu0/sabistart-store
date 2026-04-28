from django.urls import path

from system.feature_marketplace import views


app_name = "feature_marketplace"


urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("features/create/", views.feature_create, name="feature_create"),
    path("features/<slug:code>/", views.feature_detail, name="feature_detail"),
    path("categories/", views.categories, name="categories"),
    path("pricing/", views.pricing, name="pricing"),
    path("bundles/", views.bundles, name="bundles"),
    path("campaigns/", views.campaigns, name="campaigns"),
    path("coupons/", views.coupons, name="coupons"),
    path("purchases/", views.purchases, name="purchases"),
    path("tenants/", views.tenants, name="tenants"),
    path("tenants/<str:schema_name>/", views.tenant_detail, name="tenant_detail"),
    path("guide/", views.guide, name="guide"),
    path("checkout/<str:purchase_reference>/", views.checkout_session, name="checkout_session"),
]
