from django.db import models
from django.utils.text import slugify


class FAQEntry(models.Model):
    question = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=255,
        unique=True,
        help_text="URL-friendly version (auto-generated from the question).",
    )
    answer = models.TextField(help_text="FAQ answer content (supports HTML).")
    sort_order = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(
        default=True,
        help_text="Turn this FAQ on or off without deleting it.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "faq_entries"
        ordering = ["sort_order", "question"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_enabled"]),
            models.Index(fields=["sort_order"]),
        ]

    def __str__(self):
        return self.question

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.question)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f"/help/faq/{self.slug}/"
