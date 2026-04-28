from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class BlogPost(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("hidden", "Hidden"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="URL-friendly version (auto-generated from title)",
    )
    excerpt = models.TextField(
        max_length=320,
        blank=True,
        help_text="Short summary used on blog listings and previews.",
    )
    content = models.TextField(help_text="Post content (supports HTML).")
    featured_image = models.ImageField(
        upload_to="blog/",
        blank=True,
        null=True,
        help_text="Cover image shown on blog cards and post headers.",
    )
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        help_text="SEO title (defaults to post title).",
    )
    meta_description = models.TextField(
        max_length=160,
        blank=True,
        help_text="SEO description for search results.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Turn this post on or off without deleting it.",
    )
    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "blog_posts"
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status"]),
            models.Index(fields=["is_enabled"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if not self.meta_title:
            self.meta_title = self.title
        if self.status == "published" and not self.published_at:
            self.published_at = timezone.now()
        if self.status != "published" and self.published_at and self.status == "draft":
            self.published_at = None
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f"/blog/{self.slug}/"
