from __future__ import annotations

from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST

from dashboard.content_manager.forms import (
    BlogConfigurationForm,
    BlogPostForm,
    FAQEntryForm,
    GenericPageForm,
    ManagedPageForm,
)
from dashboard.decorators import dashboard_prefix_required
from dashboard.sidebar_utiles import main_sidebar
from dashboard.store_settings.content_services import (
    MANAGED_PAGE_DEFINITIONS,
    get_or_create_blog_settings,
    get_or_create_managed_page,
    list_managed_pages,
)
from dashboard.store_settings.models import BlogPost, CustomPage, FAQEntry


def _ctx(prefix: str, page_title: str, active_menu: str, **extra):
    context = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix, active_menu),
    }
    context.update(extra)
    return context


def _public_url_or_blank(route_name: str, **kwargs) -> str:
    try:
        return reverse(route_name, kwargs=kwargs)
    except NoReverseMatch:
        return ""


def _group_managed_pages():
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for definition, page, public_url in list_managed_pages():
        grouped.setdefault(definition.section, []).append(
            {
                "definition": definition,
                "page": page,
                "public_url": public_url,
            }
        )
    return grouped


@login_required
@dashboard_prefix_required
def overview(request: HttpRequest, prefix: str) -> HttpResponse:
    blog_settings = get_or_create_blog_settings()
    context = _ctx(
        prefix,
        "Content Center",
        "store_content_overview",
        managed_page_count=len(MANAGED_PAGE_DEFINITIONS),
        enabled_managed_page_count=CustomPage.objects.exclude(page_kind="generic").filter(is_enabled=True, status="published").count(),
        custom_page_count=CustomPage.objects.filter(page_kind="generic").count(),
        enabled_custom_page_count=CustomPage.objects.filter(page_kind="generic", is_enabled=True, status="published").count(),
        blog_post_count=BlogPost.objects.count(),
        published_blog_post_count=BlogPost.objects.filter(status="published", is_enabled=True).count(),
        faq_count=FAQEntry.objects.count(),
        enabled_faq_count=FAQEntry.objects.filter(is_enabled=True).count(),
        blog_settings=blog_settings,
        recent_posts=BlogPost.objects.order_by("-updated_at")[:5],
        recent_pages=CustomPage.objects.order_by("-updated_at")[:5],
        recent_faqs=FAQEntry.objects.order_by("sort_order", "question")[:5],
    )
    return render(request, "dashboard/content_manager/overview.html", context)


@login_required
@dashboard_prefix_required
def managed_pages(request: HttpRequest, prefix: str) -> HttpResponse:
    context = _ctx(
        prefix,
        "Policies & Info Pages",
        "store_content_pages",
        grouped_pages=_group_managed_pages(),
    )
    return render(request, "dashboard/content_manager/managed_pages.html", context)


@login_required
@dashboard_prefix_required
def managed_page_edit(request: HttpRequest, prefix: str, page_kind: str) -> HttpResponse:
    try:
        page = get_or_create_managed_page(page_kind)
    except KeyError as exc:
        raise Http404("Unknown managed page type.") from exc

    definition = next(item for item in MANAGED_PAGE_DEFINITIONS if item.key == page_kind)
    if request.method == "POST":
        form = ManagedPageForm(request.POST, request.FILES, instance=page)
        if form.is_valid():
            form.save()
            messages.success(request, f"{definition.title} updated.")
            return redirect("dashboard:content_manager:managed_pages", prefix=prefix)
    else:
        form = ManagedPageForm(instance=page)

    context = _ctx(
        prefix,
        definition.title,
        "store_content_pages",
        form=form,
        object=page,
        definition=definition,
        cancel_url=reverse("dashboard:content_manager:managed_pages", kwargs={"prefix": prefix}),
        public_url=_public_url_or_blank(definition.route_name),
        form_heading=f"Edit {definition.title}",
        form_intro=definition.description,
    )
    return render(request, "dashboard/content_manager/form.html", context)


@login_required
@dashboard_prefix_required
def custom_pages(request: HttpRequest, prefix: str) -> HttpResponse:
    pages = CustomPage.objects.filter(page_kind="generic").order_by("title")
    context = _ctx(
        prefix,
        "Custom Pages",
        "store_content_custom_pages",
        pages=pages,
        create_url=reverse("dashboard:content_manager:custom_page_create", kwargs={"prefix": prefix}),
    )
    return render(request, "dashboard/content_manager/custom_pages.html", context)


@login_required
@dashboard_prefix_required
def custom_page_create(request: HttpRequest, prefix: str) -> HttpResponse:
    if request.method == "POST":
        form = GenericPageForm(request.POST, request.FILES)
        if form.is_valid():
            page = form.save(commit=False)
            page.page_kind = "generic"
            page.save()
            messages.success(request, "Custom page created.")
            return redirect("dashboard:content_manager:custom_pages", prefix=prefix)
    else:
        form = GenericPageForm(initial={"status": "draft", "is_enabled": True})

    context = _ctx(
        prefix,
        "New Custom Page",
        "store_content_custom_pages",
        form=form,
        cancel_url=reverse("dashboard:content_manager:custom_pages", kwargs={"prefix": prefix}),
        form_heading="Create custom page",
        form_intro="Publish storefront pages like About Us, Size Guide, or any other informational page your store needs.",
    )
    return render(request, "dashboard/content_manager/form.html", context)


@login_required
@dashboard_prefix_required
def custom_page_edit(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    page = get_object_or_404(CustomPage, pk=pk, page_kind="generic")
    if request.method == "POST":
        form = GenericPageForm(request.POST, request.FILES, instance=page)
        if form.is_valid():
            page = form.save(commit=False)
            page.page_kind = "generic"
            page.save()
            messages.success(request, "Custom page updated.")
            return redirect("dashboard:content_manager:custom_pages", prefix=prefix)
    else:
        form = GenericPageForm(instance=page)

    context = _ctx(
        prefix,
        page.title,
        "store_content_custom_pages",
        form=form,
        object=page,
        cancel_url=reverse("dashboard:content_manager:custom_pages", kwargs={"prefix": prefix}),
        public_url=_public_url_or_blank("content:custom_page", page_slug=page.slug),
        form_heading=f"Edit {page.title}",
        form_intro="Update the content, SEO, and visibility of this custom storefront page.",
    )
    return render(request, "dashboard/content_manager/form.html", context)


@login_required
@dashboard_prefix_required
@require_POST
def custom_page_toggle(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    page = get_object_or_404(CustomPage, pk=pk, page_kind="generic")
    page.is_enabled = not page.is_enabled
    page.save(update_fields=["is_enabled", "updated_at"])
    messages.success(request, f"{page.title} is now {'enabled' if page.is_enabled else 'disabled'}.")
    return redirect("dashboard:content_manager:custom_pages", prefix=prefix)


@login_required
@dashboard_prefix_required
@require_POST
def custom_page_delete(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    page = get_object_or_404(CustomPage, pk=pk, page_kind="generic")
    title = page.title
    page.delete()
    messages.success(request, f"{title} deleted.")
    return redirect("dashboard:content_manager:custom_pages", prefix=prefix)


@login_required
@dashboard_prefix_required
def blog_settings(request: HttpRequest, prefix: str) -> HttpResponse:
    settings = get_or_create_blog_settings()
    if request.method == "POST":
        form = BlogConfigurationForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Blog settings updated.")
            return redirect("dashboard:content_manager:blog_settings", prefix=prefix)
    else:
        form = BlogConfigurationForm(instance=settings)

    context = _ctx(
        prefix,
        "Blog Settings",
        "store_content_blog",
        form=form,
        object=settings,
        cancel_url=reverse("dashboard:content_manager:blog_posts", kwargs={"prefix": prefix}),
        public_url=_public_url_or_blank("content:blog_index"),
        form_heading="Manage blog settings",
        form_intro="Turn your blog on or off and control the main storefront presentation settings visitors see.",
    )
    return render(request, "dashboard/content_manager/form.html", context)


@login_required
@dashboard_prefix_required
def blog_posts(request: HttpRequest, prefix: str) -> HttpResponse:
    settings = get_or_create_blog_settings()
    posts = BlogPost.objects.order_by("-updated_at")
    context = _ctx(
        prefix,
        "Blog Posts",
        "store_content_blog",
        posts=posts,
        blog_settings=settings,
        create_url=reverse("dashboard:content_manager:blog_post_create", kwargs={"prefix": prefix}),
        settings_url=reverse("dashboard:content_manager:blog_settings", kwargs={"prefix": prefix}),
        public_url=_public_url_or_blank("content:blog_index"),
    )
    return render(request, "dashboard/content_manager/blog_posts.html", context)


@login_required
@dashboard_prefix_required
def blog_post_create(request: HttpRequest, prefix: str) -> HttpResponse:
    if request.method == "POST":
        form = BlogPostForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Blog post created.")
            return redirect("dashboard:content_manager:blog_posts", prefix=prefix)
    else:
        form = BlogPostForm(initial={"status": "draft", "is_enabled": True})

    context = _ctx(
        prefix,
        "New Blog Post",
        "store_content_blog",
        form=form,
        cancel_url=reverse("dashboard:content_manager:blog_posts", kwargs={"prefix": prefix}),
        form_heading="Create blog post",
        form_intro="Publish articles, announcements, buying guides, and editorial updates for your storefront.",
    )
    return render(request, "dashboard/content_manager/form.html", context)


@login_required
@dashboard_prefix_required
def blog_post_edit(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    post = get_object_or_404(BlogPost, pk=pk)
    if request.method == "POST":
        form = BlogPostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, "Blog post updated.")
            return redirect("dashboard:content_manager:blog_posts", prefix=prefix)
    else:
        form = BlogPostForm(instance=post)

    context = _ctx(
        prefix,
        post.title,
        "store_content_blog",
        form=form,
        object=post,
        cancel_url=reverse("dashboard:content_manager:blog_posts", kwargs={"prefix": prefix}),
        public_url=_public_url_or_blank("content:blog_post", post_slug=post.slug),
        form_heading=f"Edit {post.title}",
        form_intro="Update the story, SEO, and publishing state for this blog post.",
    )
    return render(request, "dashboard/content_manager/form.html", context)


@login_required
@dashboard_prefix_required
@require_POST
def blog_post_toggle(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    post = get_object_or_404(BlogPost, pk=pk)
    post.is_enabled = not post.is_enabled
    post.save(update_fields=["is_enabled", "updated_at"])
    messages.success(request, f"{post.title} is now {'enabled' if post.is_enabled else 'disabled'}.")
    return redirect("dashboard:content_manager:blog_posts", prefix=prefix)


@login_required
@dashboard_prefix_required
@require_POST
def blog_post_delete(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    post = get_object_or_404(BlogPost, pk=pk)
    title = post.title
    post.delete()
    messages.success(request, f"{title} deleted.")
    return redirect("dashboard:content_manager:blog_posts", prefix=prefix)


@login_required
@dashboard_prefix_required
def faqs(request: HttpRequest, prefix: str) -> HttpResponse:
    help_center_page = get_or_create_managed_page("help_center")
    entries = FAQEntry.objects.order_by("sort_order", "question")
    context = _ctx(
        prefix,
        "FAQs",
        "store_content_faq",
        help_center_page=help_center_page,
        faqs=entries,
        create_url=reverse("dashboard:content_manager:faq_create", kwargs={"prefix": prefix}),
        help_center_url=reverse("dashboard:content_manager:managed_page_edit", kwargs={"prefix": prefix, "page_kind": "help_center"}),
        public_url=_public_url_or_blank("support:help_center"),
    )
    return render(request, "dashboard/content_manager/faqs.html", context)


@login_required
@dashboard_prefix_required
def faq_create(request: HttpRequest, prefix: str) -> HttpResponse:
    if request.method == "POST":
        form = FAQEntryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "FAQ created.")
            return redirect("dashboard:content_manager:faqs", prefix=prefix)
    else:
        form = FAQEntryForm(initial={"is_enabled": True})

    context = _ctx(
        prefix,
        "New FAQ",
        "store_content_faq",
        form=form,
        cancel_url=reverse("dashboard:content_manager:faqs", kwargs={"prefix": prefix}),
        form_heading="Create FAQ entry",
        form_intro="Add a question and answer for the public help center.",
    )
    return render(request, "dashboard/content_manager/form.html", context)


@login_required
@dashboard_prefix_required
def faq_edit(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    faq = get_object_or_404(FAQEntry, pk=pk)
    if request.method == "POST":
        form = FAQEntryForm(request.POST, instance=faq)
        if form.is_valid():
            form.save()
            messages.success(request, "FAQ updated.")
            return redirect("dashboard:content_manager:faqs", prefix=prefix)
    else:
        form = FAQEntryForm(instance=faq)

    context = _ctx(
        prefix,
        faq.question,
        "store_content_faq",
        form=form,
        object=faq,
        cancel_url=reverse("dashboard:content_manager:faqs", kwargs={"prefix": prefix}),
        public_url=_public_url_or_blank("support:faq_detail", faq_slug=faq.slug),
        form_heading="Edit FAQ",
        form_intro="Update this public help center question and answer.",
    )
    return render(request, "dashboard/content_manager/form.html", context)


@login_required
@dashboard_prefix_required
@require_POST
def faq_toggle(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    faq = get_object_or_404(FAQEntry, pk=pk)
    faq.is_enabled = not faq.is_enabled
    faq.save(update_fields=["is_enabled", "updated_at"])
    messages.success(request, f"FAQ is now {'enabled' if faq.is_enabled else 'disabled'}.")
    return redirect("dashboard:content_manager:faqs", prefix=prefix)


@login_required
@dashboard_prefix_required
@require_POST
def faq_delete(request: HttpRequest, prefix: str, pk: int) -> HttpResponse:
    faq = get_object_or_404(FAQEntry, pk=pk)
    question = faq.question
    faq.delete()
    messages.success(request, f"FAQ deleted: {question}")
    return redirect("dashboard:content_manager:faqs", prefix=prefix)
