from django.urls import path
from . import views

app_name = 'search'

urlpatterns = [
    path('', views.search_results_view, name='search_results'),
    path('advanced/', views.advanced_search_view, name='advanced_search'),
    path('visual/', views.visual_search_view, name='visual_search'),
    path('tags/<slug:tag_slug>/', views.tag_browse_view, name='tag_browse'),
    path('filter/', views.filtered_browse_view, name='filtered_browse'),
]
