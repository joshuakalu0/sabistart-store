from django.urls import path

from system.theme_marketplace import views


app_name = "theme_marketplace"


urlpatterns = [
    path("", views.home, name="home"),
    path("create/", views.create, name="create"),
    path("sync/", views.sync_catalog, name="sync"),
    path("categories/", views.categories, name="categories"),
    path("<uuid:theme_id>/", views.detail, name="detail"),
]
