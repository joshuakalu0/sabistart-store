from django.urls import path

from . import views


app_name = "analytics"


urlpatterns = [
    path("", views.overview, name="overview"),
    path("orders/", views.orders, name="orders"),
    path("products/", views.products, name="products"),
    path("inventory/", views.inventory, name="inventory"),
    path("customers/", views.customers, name="customers"),
    path("<str:page_key>/data/", views.data, name="data"),
    path("<str:page_key>/drilldown/", views.drilldown, name="drilldown"),
]
