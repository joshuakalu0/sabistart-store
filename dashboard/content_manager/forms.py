from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from dashboard.store_settings.models import BlogPost, BlogSettings, CustomPage, FAQEntry
from sabistart.ui.forms import TailwindFormMixin


class ManagedPageForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CustomPage
        fields = [
            "title",
            "content",
            "excerpt",
            "template",
            "show_title",
            "show_breadcrumbs",
            "featured_image",
            "meta_title",
            "meta_description",
            "status",
            "is_enabled",
        ]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 14}),
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "meta_description": forms.Textarea(attrs={"rows": 3}),
        }


class GenericPageForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CustomPage
        fields = [
            "title",
            "slug",
            "content",
            "excerpt",
            "template",
            "show_title",
            "show_breadcrumbs",
            "featured_image",
            "meta_title",
            "meta_description",
            "status",
            "is_enabled",
        ]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 14}),
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "meta_description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get("slug") or slugify(self.cleaned_data.get("title", ""))
        if not slug:
            raise ValidationError("Add a title or slug for this page.")
        queryset = CustomPage.objects.filter(slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise ValidationError("A page with this slug already exists.")
        return slug


class BlogConfigurationForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = BlogSettings
        fields = [
            "enable_blog",
            "blog_title",
            "blog_description",
            "posts_per_page",
            "layout",
            "show_featured_image",
            "show_excerpt",
            "show_read_more_button",
            "show_categories",
            "show_tags",
            "enable_comments",
            "show_breadcrumbs",
        ]
        widgets = {
            "blog_description": forms.Textarea(attrs={"rows": 3}),
        }


class BlogPostForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = [
            "title",
            "slug",
            "excerpt",
            "content",
            "featured_image",
            "meta_title",
            "meta_description",
            "status",
            "is_enabled",
        ]
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "content": forms.Textarea(attrs={"rows": 16}),
            "meta_description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get("slug") or slugify(self.cleaned_data.get("title", ""))
        if not slug:
            raise ValidationError("Add a title or slug for this post.")
        queryset = BlogPost.objects.filter(slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise ValidationError("A blog post with this slug already exists.")
        return slug


class FAQEntryForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = FAQEntry
        fields = [
            "question",
            "slug",
            "answer",
            "sort_order",
            "is_enabled",
        ]
        widgets = {
            "answer": forms.Textarea(attrs={"rows": 10}),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get("slug") or slugify(self.cleaned_data.get("question", ""))
        if not slug:
            raise ValidationError("Add a question or slug for this FAQ.")
        queryset = FAQEntry.objects.filter(slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise ValidationError("An FAQ with this slug already exists.")
        return slug
