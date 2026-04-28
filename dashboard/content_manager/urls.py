from django.urls import path

from dashboard.content_manager import views


app_name = "content_manager"


urlpatterns = [
    path("", views.overview, name="overview"),
    path("pages/", views.managed_pages, name="managed_pages"),
    path("pages/<slug:page_kind>/", views.managed_page_edit, name="managed_page_edit"),
    path("custom-pages/", views.custom_pages, name="custom_pages"),
    path("custom-pages/new/", views.custom_page_create, name="custom_page_create"),
    path("custom-pages/<int:pk>/edit/", views.custom_page_edit, name="custom_page_edit"),
    path("custom-pages/<int:pk>/toggle/", views.custom_page_toggle, name="custom_page_toggle"),
    path("custom-pages/<int:pk>/delete/", views.custom_page_delete, name="custom_page_delete"),
    path("blog/", views.blog_posts, name="blog_posts"),
    path("blog/settings/", views.blog_settings, name="blog_settings"),
    path("blog/posts/new/", views.blog_post_create, name="blog_post_create"),
    path("blog/posts/<int:pk>/edit/", views.blog_post_edit, name="blog_post_edit"),
    path("blog/posts/<int:pk>/toggle/", views.blog_post_toggle, name="blog_post_toggle"),
    path("blog/posts/<int:pk>/delete/", views.blog_post_delete, name="blog_post_delete"),
    path("faqs/", views.faqs, name="faqs"),
    path("faqs/new/", views.faq_create, name="faq_create"),
    path("faqs/<int:pk>/edit/", views.faq_edit, name="faq_edit"),
    path("faqs/<int:pk>/toggle/", views.faq_toggle, name="faq_toggle"),
    path("faqs/<int:pk>/delete/", views.faq_delete, name="faq_delete"),
]
