from django.http import Http404

from dashboard.store_settings.content_services import (
    get_public_blog_post,
    get_public_blog_posts,
    get_public_custom_page,
)
from public.storefront.services import build_breadcrumbs, render_info_page, render_storefront


def blog_index_view(request):
    settings, posts = get_public_blog_posts()
    if not settings.enable_blog:
        raise Http404("The blog is disabled.")
    posts = list(posts[: settings.posts_per_page])
    return render_storefront(
        request,
        "content/blog_index.html",
        {
            "blog_config": settings,
            "blog_entries": posts,
            "breadcrumbs": build_breadcrumbs(("Home", "/"), (settings.blog_title or "Blog", "")),
        },
        page_title=settings.blog_title or "Blog",
        page_description=settings.blog_description or "Store stories, updates, and articles.",
    )


def blog_post_view(request, post_slug):
    settings, post = get_public_blog_post(post_slug)
    if not settings.enable_blog or post is None:
        raise Http404("This post is not available.")
    related_posts = [
        candidate
        for candidate in get_public_blog_posts()[1].exclude(pk=post.pk)[:3]
    ]
    return render_storefront(
        request,
        "content/blog_post.html",
        {
            "blog_config": settings,
            "entry": post,
            "related_entries": related_posts,
            "breadcrumbs": build_breadcrumbs(("Home", "/"), (settings.blog_title or "Blog", "/blog/"), (post.title, "")),
        },
        page_title=post.meta_title or post.title,
        page_description=post.meta_description or post.excerpt or post.title,
    )


def buying_guide_view(request, guide_slug):
    return render_info_page(
        request,
        title="Buying Guide",
        body="Buying guides are rendered as themed content shells in this implementation.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Guides", "/guides/"), (guide_slug, ""))},
    )


def lookbook_view(request):
    return render_info_page(
        request,
        title="Lookbook",
        body="Lookbook content can be layered into this themed route without changing storefront navigation.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Lookbook", ""))},
    )


def lookbook_detail_view(request, look_slug):
    return render_info_page(
        request,
        title=look_slug.replace("-", " ").title(),
        body="This lookbook detail page is ready for media-backed editorial content.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Lookbook", "/lookbook/"), (look_slug, ""))},
    )


def video_gallery_view(request):
    return render_info_page(
        request,
        title="Video Gallery",
        body="Video gallery rendering is in place as a themed shell.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Video Gallery", ""))},
    )


def user_generated_content_view(request):
    return render_info_page(
        request,
        title="Community Gallery",
        body="User-generated content is represented as a themed shell until moderation and media ingestion are added.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Community Gallery", ""))},
    )


def product_qa_view(request, product_slug):
    return render_info_page(
        request,
        title="Product Q&A",
        body=f"Questions and answers for {product_slug} are reserved for a later phase.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Q&A", ""))},
    )


def submit_review_view(request, product_slug):
    return render_info_page(
        request,
        title="Submit Review",
        body=f"Review submission for {product_slug} is displayed as a themed shell until review persistence is enabled.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Reviews", ""))},
    )


def custom_page_view(request, page_slug):
    page = get_public_custom_page(page_slug)
    if page is None:
        raise Http404("This page is not available.")
    return render_storefront(
        request,
        "shared/content_page.html",
        {
            "page": page,
            "headline": page.title,
            "breadcrumbs": build_breadcrumbs(("Home", "/"), (page.title, "")) if page.show_breadcrumbs else [],
        },
        page_title=page.meta_title or page.title,
        page_description=page.meta_description or page.excerpt or page.title,
    )
