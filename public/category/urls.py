from django.urls import path
from . import views

app_name = 'category'

urlpatterns = [
    path('shop/', views.shop_all_view, name='shop_all'),
    path('c/<slug:category_slug>/', views.category_detail_view, name='category_detail'),
    path('c/<slug:category_slug>/<slug:subcategory_slug>/', views.subcategory_detail_view, name='subcategory_detail'),
    path('brands/', views.brands_directory_view, name='brands_directory'),
    path('brands/<slug:brand_slug>/', views.brand_detail_view, name='brand_detail'),
    path('collections/', views.collections_list_view, name='collections_list'),
    path('collections/<slug:collection_slug>/', views.collection_detail_view, name='collection_detail'),
    path('new-arrivals/', views.new_arrivals_view, name='new_arrivals'),
    path('best-sellers/', views.best_sellers_view, name='best_sellers'),
    path('trending/', views.trending_view, name='trending'),
    path('deals/', views.deals_view, name='deals'),
    path('flash-sale/', views.flash_sale_view, name='flash_sale'),
    path('clearance/', views.clearance_view, name='clearance'),
    path('gifts/', views.gift_guide_view, name='gift_guide'),
]
