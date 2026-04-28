from django.urls import path
from . import views

app_name = 'themes'

urlpatterns = [
    path("marketplace/", views.marketplace, name="marketplace"),
    path("marketplace/<uuid:theme_id>/", views.theme_detail, name="theme_detail"),
    path("acquire/<uuid:theme_id>/", views.acquire_theme, name="acquire"),
    path("install/<uuid:theme_id>/", views.install_theme, name="install"),
    path("configure/<uuid:theme_id>/", views.configure_theme, name="configure"),

    path("installed/", views.installed_themes, name="installed"),
    path("activate/<uuid:theme_id>/", views.activate_theme, name="activate"),
    path("deactivate/<uuid:theme_id>/", views.deactivate_theme, name="deactivate"),
    path("disable/<uuid:theme_id>/", views.disable_theme, name="disable"),
    path("remove/<uuid:theme_id>/", views.remove_theme, name="remove"),

    path("edit/<uuid:theme_id>/<str:page_name>/", views.page_editor, name="page_editor"),
    path("preview/<uuid:theme_id>/<str:page_name>/", views.preview_theme, name="preview"),
]
