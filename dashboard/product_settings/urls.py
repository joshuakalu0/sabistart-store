from django.urls import path
from . import views
from . import product_view

app_name = 'product_settings'

urlpatterns = [
    # Attribute Groups
    path('attribute-groups/', views.attribute_group_list,
         name='attribute_group_list'),
    path('attribute-groups/create/', views.attribute_group_create,
         name='attribute_group_create'),
    path('attribute-groups/<uuid:pk>/edit/',
         views.attribute_group_edit, name='attribute_group_edit'),
    path('attribute-groups/<uuid:pk>/delete/',
         views.attribute_group_delete, name='attribute_group_delete'),

    # Attributes
    path('attributes/', views.attribute_list, name='attribute_list'),
    path('attributes/create/', views.attribute_create, name='attribute_create'),
    path('attributes/<uuid:pk>/edit/',
         views.attribute_edit, name='attribute_edit'),
    path('attributes/<uuid:pk>/delete/',
         views.attribute_delete, name='attribute_delete'),
    path('attributes/<uuid:attribute_id>/values/',
         views.attribute_value_list, name='attribute_value_list'),
    path('attributes/<uuid:attribute_id>/values/create/',
         views.attribute_value_create, name='attribute_value_create'),
    path('attributes/values/<uuid:pk>/edit/',
         views.attribute_value_edit, name='attribute_value_edit'),
    path('attributes/values/<uuid:pk>/delete/',
         views.attribute_value_delete, name='attribute_value_delete'),
    path('products/<uuid:pk>/details/',
         views.product_details, name='product_details'),
    path('attributes/<uuid:pk>/details/',
         views.attribute_details, name='attribute_details'),
    path('attribute-groups/<uuid:pk>/details/',
         views.attribute_group_details, name='attribute_group_details'),
    path('attributes/values/<uuid:pk>/details/',
         views.attribute_value_details, name='attribute_value_details'),

    # Products
    path('', views.product_list, name='product_list'),
    path('create/', views.product_create, name='product_create'),
    #     path('creat/', product_view.product_create, name='product_create'),
    path('attributes_values/<uuid:attribute_id>/values/',
         product_view.get_attribute_values, name='product_create'),
    path('<uuid:pk>/edit/', views.product_edit, name='product_edit'),

    #     path('<uuid:pk>/update/', views.product_update, name='product_update'),
    path('<uuid:pk>/delete/', views.product_delete, name='product_delete'),

    # AJAX Utilities
    path('ajax/generate-slug/', views.generate_slug, name='generate_slug'),
]
