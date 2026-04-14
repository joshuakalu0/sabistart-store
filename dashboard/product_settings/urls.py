from django.urls import path
from . import views

app_name = 'product_settings'

urlpatterns = [
    # Attribute Groups
    path('attribute-groups/', views.attribute_group_list, name='attribute_group_list'),
    path('attribute-groups/create/', views.attribute_group_create, name='attribute_group_create'),
    path('attribute-groups/<uuid:pk>/edit/', views.attribute_group_edit, name='attribute_group_edit'),
    path('attribute-groups/<uuid:pk>/delete/', views.attribute_group_delete, name='attribute_group_delete'),

    # Attributes
    path('attributes/', views.attribute_list, name='attribute_list'),
    path('attributes/create/', views.attribute_create, name='attribute_create'),
    path('attributes/<uuid:pk>/edit/', views.attribute_edit, name='attribute_edit'),
    path('attributes/<uuid:pk>/delete/', views.attribute_delete, name='attribute_delete'),

    # Products
    path('', views.product_list, name='product_list'),
    path('create/', views.product_create, name='product_create'),
    path('<uuid:pk>/edit/', views.product_edit, name='product_edit'),
    path('<uuid:pk>/delete/', views.product_delete, name='product_delete'),

    # AJAX Utilities
    path('ajax/generate-slug/', views.generate_slug, name='generate_slug'),
]