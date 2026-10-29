from django.db import models
from django.utils.text import slugify
from dashboard.settings.models import AuditModel
import uuid


from django.utils.crypto import get_random_string


def generate_unique_slug(model_cls, name, instance_pk=None, fallback='item'):
    base_slug = slugify(name) if name else ''
    if not base_slug:
        base_slug = fallback
    suffix = get_random_string(6, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')
    candidate = f"{base_slug}-{suffix}"
    qs = model_cls.objects.filter(slug=candidate)
    if instance_pk:
        qs = qs.exclude(pk=instance_pk)
    while qs.exists():
        suffix = get_random_string(6, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')
        candidate = f"{base_slug}-{suffix}"
        qs = model_cls.objects.filter(slug=candidate)
        if instance_pk:
            qs = qs.exclude(pk=instance_pk)
    return candidate


# ============================================================================
# CORE: CATEGORIES & TAXONOMIES
# ============================================================================

class Category(AuditModel):
    """
    Hierarchical product categorization with unlimited depth.
    Supports multiple classification hierarchies.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')

    # Content
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to='categories/%Y/%m/', blank=True, null=True)
    icon = models.CharField(max_length=100, blank=True,
                            help_text="CSS icon class or emoji")

    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(max_length=500, blank=True)
    meta_keywords = models.TextField(blank=True)
    canonical_url = models.URLField(blank=True)

    # Display
    display_order = models.IntegerField(default=0, db_index=True)  # ❌❌
    featured = models.BooleanField(default=False, db_index=True)  # ❌❌
    show_in_menu = models.BooleanField(default=True)  # ❌❌
    menu_order = models.IntegerField(default=0)  # ❌❌

    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    is_visible = models.BooleanField(default=True)  # ❌❌

    # Analytics
    view_count = models.PositiveBigIntegerField(default=0)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['parent', 'is_active', 'display_order']),
            models.Index(fields=['slug', 'is_active']),
            models.Index(fields=['featured', 'is_active']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(Category, self.name, instance_pk=self.pk, fallback='category')
        super().save(*args, **kwargs)


class Tag(AuditModel):
    """Product tags for flexible classification"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    color = models.CharField(max_length=7, default='#000000')
    icon = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)  # ❌❌

    # SEO
    meta_title = models.CharField(max_length=255, blank=True)  # ❌❌
    meta_description = models.TextField(max_length=500, blank=True)  # ❌❌

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(Tag, self.name, instance_pk=self.pk, fallback='tag')
        super().save(*args, **kwargs)


# ============================================================================
# CORE: BRANDS & MANUFACTURERS
# ============================================================================

class Brand(AuditModel):
    """Brand/Manufacturer management"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)

    # Content
    description = models.TextField(blank=True)  # ❌❌
    story = models.TextField(blank=True, help_text="Brand story/about")  # ❌❌
    logo = models.ImageField(upload_to='brands/%Y/%m/', blank=True, null=True)
    banner = models.ImageField(
        upload_to='brands/banners/%Y/%m/', blank=True, null=True)  # ❌❌

    # Contact
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)

    # Social
    facebook = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)

    # SEO
    meta_title = models.CharField(max_length=255, blank=True)  # ❌❌
    meta_description = models.TextField(max_length=500, blank=True)  # ❌❌
    meta_keywords = models.TextField(blank=True)  # ❌❌

    # Display
    featured = models.BooleanField(default=False, db_index=True) 
    display_order = models.IntegerField(default=0)

    # Status
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(Brand, self.name, instance_pk=self.pk, fallback='brand')
        super().save(*args, **kwargs)
