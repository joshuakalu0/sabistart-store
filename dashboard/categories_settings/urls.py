from django.urls import path
from dashboard.categories_settings import views

app_name = 'dashboard_categories'

urlpatterns = [
    # Category URLs
    path('', views.category_list, name='list'),
    path('create/', views.category_create, name='create'),
    path('<uuid:category_id>/edit/', views.category_edit, name='edit'),
    path('<uuid:category_id>/delete/', views.category_delete, name='delete'),

    # Tag URLs
    path('tags/', views.tag_list, name='tag_list'),
    path('tags/create/', views.tag_create, name='tag_create'),
    path('tags/_create/', views.ajax_create_tag, name='tag_create'),
    path('tags/<uuid:tag_id>/edit/', views.tag_edit, name='tag_edit'),
    path('tags/<uuid:tag_id>/delete/', views.tag_delete, name='tag_delete'),

    # Brand URLs
    path('brands/', views.brand_list, name='brand_list'),
    path('brands/create/', views.brand_create, name='brand_create'),
    path('brands/<uuid:brand_id>/edit/', views.brand_edit, name='brand_edit'),
    path('brands/<uuid:brand_id>/delete/',
         views.brand_delete, name='brand_delete'),
    path('categories/<uuid:category_id>/details/',
         views.category_details, name='category_details'),
    path('tags/<uuid:tag_id>/details/', views.tag_details, name='tag_details'),
    path('brands/<uuid:brand_id>/details/',
         views.brand_details, name='brand_details'),
]
