from django.urls import path
from . import views

app_name = 'content'

urlpatterns = [
    path('blog/', views.blog_index_view, name='blog_index'),
    path('blog/<slug:post_slug>/', views.blog_post_view, name='blog_post'),
    path('pages/<slug:page_slug>/', views.custom_page_view, name='custom_page'),
    path('guides/<slug:guide_slug>/', views.buying_guide_view, name='buying_guide'),
    path('lookbook/', views.lookbook_view, name='lookbook'),
    path('lookbook/<slug:look_slug>/', views.lookbook_detail_view, name='lookbook_detail'),
    path('video-gallery/', views.video_gallery_view, name='video_gallery'),
    path('ugc/', views.user_generated_content_view, name='ugc_gallery'),
    path('qa/<slug:product_slug>/', views.product_qa_view, name='product_qa'),
    path('reviews/<slug:product_slug>/submit/', views.submit_review_view, name='submit_review'),
]
