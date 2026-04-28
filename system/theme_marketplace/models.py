from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Theme(models.Model):
    """Shared storefront theme catalog entry backed by a central theme slug."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING = "pending", _("Pending Review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        SUSPENDED = "suspended", _("Suspended")

    class Source(models.TextChoices):
        BUILTIN = "builtin", _("Built-in")
        UPLOADED = "uploaded", _("Uploaded / Legacy")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_themes",
    )
    category = models.ForeignKey(
        "theme_marketplace.ThemeCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="themes",
    )

    name = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=20, default="1.0.0")
    currency = models.CharField(max_length=3, default="NGN")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_free = models.BooleanField(default=True)

    source = models.CharField(max_length=20, choices=Source.choices, default=Source.BUILTIN, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_published = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False)
    preview_image_path = models.CharField(max_length=500, blank=True)
    thumbnail_path = models.CharField(max_length=500, blank=True)
    demo_url = models.URLField(blank=True)
    schema_path = models.CharField(max_length=500, blank=True)
    changelog_path = models.CharField(max_length=500, blank=True)
    feature_bullets = models.JSONField(default=list, blank=True)
    preview_gallery = models.JSONField(default=list, blank=True)
    manifest = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_internal = models.BooleanField(default=False, db_index=True)

    # Legacy compatibility fields; runtime rendering must use slug + shared themes directory.
    zip_file = models.FileField(upload_to="themes/uploads/", blank=True)
    thumbnail = models.ImageField(upload_to="themes/thumbnails/", blank=True)
    folder_path = models.CharField(max_length=500, blank=True)

    downloads = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "shared_themes"
        verbose_name = _("Theme")
        verbose_name_plural = _("Themes")
        ordering = ["-is_featured", "name"]

    def __str__(self):
        return f"{self.name} v{self.version}"


class ThemeBasePage(models.Model):
    """Logical storefront template paths supplied by a theme manifest."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="base_pages")
    page_name = models.CharField(max_length=150, db_index=True)
    file_path = models.CharField(max_length=500)
    css_path = models.CharField(max_length=500, blank=True)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    is_required = models.BooleanField(default=True)

    class Meta:
        db_table = "shared_theme_pages"
        verbose_name = _("Theme Base Page")
        verbose_name_plural = _("Theme Base Pages")
        unique_together = [("theme", "page_name")]
        ordering = ["page_name"]

    def __str__(self):
        return f"{self.theme.name} - {self.page_name}"


class ThemeCategory(models.Model):
    """Shared category grouping for theme marketplace entries."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "shared_theme_categories"
        verbose_name = _("Theme Category")
        verbose_name_plural = _("Theme Categories")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ThemeOffer(models.Model):
    class OfferType(models.TextChoices):
        FREE = "free", _("Free")
        ONE_TIME = "one_time", _("One Time")
        SUBSCRIPTION = "subscription", _("Subscription")
        LIMITED_RELEASE = "limited_release", _("Limited Release")
        SEASONAL = "seasonal", _("Seasonal")
        DISCOUNT = "discount", _("Discount")

    class BillingInterval(models.TextChoices):
        NONE = "none", _("None")
        MONTHLY = "monthly", _("Monthly")
        YEARLY = "yearly", _("Yearly")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="offers")
    name = models.CharField(max_length=120)
    offer_type = models.CharField(max_length=20, choices=OfferType.choices, default=OfferType.FREE, db_index=True)
    billing_interval = models.CharField(max_length=20, choices=BillingInterval.choices, default=BillingInterval.NONE)
    currency = models.CharField(max_length=3, default="NGN")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_theme_offers"
        ordering = ["theme__name", "-is_default", "name"]

    def __str__(self):
        return f"{self.theme.name} - {self.name}"


class ThemeRelease(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="releases")
    version = models.CharField(max_length=20, db_index=True)
    title = models.CharField(max_length=160, blank=True)
    changelog = models.TextField(blank=True)
    released_at = models.DateTimeField(default=timezone.now, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "shared_theme_releases"
        ordering = ["-released_at"]
        unique_together = [("theme", "version")]

    def __str__(self):
        return f"{self.theme.name} {self.version}"


class ThemeReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="reviews")
    reviewer_name = models.CharField(max_length=120)
    reviewer_email = models.EmailField(blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    title = models.CharField(max_length=160, blank=True)
    body = models.TextField(blank=True)
    is_published = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_theme_reviews"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.theme.name} review ({self.rating}/5)"


class TenantThemeAccess(models.Model):
    """Shared access record proving a tenant can use a theme without copying its files."""

    class AccessType(models.TextChoices):
        FREE = "free", _("Free")
        PURCHASED = "purchased", _("Purchased")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(
        "core.Shop",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="theme_access_records",
    )
    schema_name = models.CharField(max_length=63, db_index=True)
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="tenant_access_records")
    access_type = models.CharField(max_length=12, choices=AccessType.choices, default=AccessType.FREE)
    acquired_at = models.DateTimeField(default=timezone.now, db_index=True)
    purchase_date = models.DateTimeField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_reference = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_tenant_theme_access"
        verbose_name = _("Tenant Theme Access")
        verbose_name_plural = _("Tenant Theme Access")
        unique_together = [("schema_name", "theme")]
        ordering = ["schema_name", "theme__name"]
        indexes = [
            models.Index(fields=["schema_name", "is_active"]),
            models.Index(fields=["theme", "is_active"]),
        ]

    def __str__(self):
        return f"{self.schema_name} -> {self.theme.slug}"


class TenantInstalledTheme(models.Model):
    class InstallStatus(models.TextChoices):
        INSTALLED = "installed", _("Installed")
        DISABLED = "disabled", _("Disabled")
        REMOVED = "removed", _("Removed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(
        "core.Shop",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="installed_themes",
    )
    schema_name = models.CharField(max_length=63, db_index=True)
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="installed_tenants")
    installed_version = models.CharField(max_length=20, blank=True)
    schema_version = models.CharField(max_length=20, blank=True)
    install_status = models.CharField(max_length=20, choices=InstallStatus.choices, default=InstallStatus.INSTALLED, db_index=True)
    default_config = models.JSONField(default=dict, blank=True)
    installed_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "shared_tenant_installed_theme"
        ordering = ["schema_name", "theme__name"]
        unique_together = [("schema_name", "theme")]

    def __str__(self):
        return f"{self.schema_name} installed {self.theme.slug}"


class TenantActiveTheme(models.Model):
    """Exactly one active theme pointer per tenant schema."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.OneToOneField(
        "core.Shop",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="active_theme_record",
    )
    schema_name = models.CharField(max_length=63, unique=True, db_index=True)
    theme = models.ForeignKey(Theme, on_delete=models.PROTECT, related_name="active_tenants")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_tenant_active_theme"
        verbose_name = _("Tenant Active Theme")
        verbose_name_plural = _("Tenant Active Themes")
        ordering = ["schema_name"]

    def __str__(self):
        return f"{self.schema_name} -> {self.theme.slug}"


class TenantThemeContent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(
        "core.Shop",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="theme_content_records",
    )
    schema_name = models.CharField(max_length=63, db_index=True)
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="tenant_content_records")
    universal_content = models.JSONField(default=dict, blank=True)
    theme_content = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_tenant_theme_content"
        ordering = ["schema_name", "theme__name"]
        unique_together = [("schema_name", "theme")]

    def __str__(self):
        return f"{self.schema_name} content for {self.theme.slug}"


class TenantThemeAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(TenantThemeContent, on_delete=models.CASCADE, related_name="assets")
    asset_key = models.CharField(max_length=120, db_index=True)
    asset_label = models.CharField(max_length=160, blank=True)
    asset_type = models.CharField(max_length=40, default="image")
    file = models.FileField(upload_to="themes/assets/%Y/%m/", blank=True)
    remote_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_tenant_theme_assets"
        ordering = ["asset_key", "-created_at"]

    def __str__(self):
        return f"{self.content.schema_name} asset {self.asset_key}"


class ThemeSwitchLog(models.Model):
    """Append-only record of theme activations and forced fallbacks."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(
        "core.Shop",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="theme_switch_logs",
    )
    schema_name = models.CharField(max_length=63, db_index=True)
    from_theme = models.ForeignKey(
        Theme,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="switches_from",
    )
    to_theme = models.ForeignKey(
        Theme,
        on_delete=models.PROTECT,
        related_name="switches_to",
    )
    switched_at = models.DateTimeField(default=timezone.now, db_index=True)
    switched_by_user_id = models.CharField(max_length=100, blank=True)
    switched_by_email = models.EmailField(blank=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "shared_theme_switch_log"
        verbose_name = _("Theme Switch Log")
        verbose_name_plural = _("Theme Switch Logs")
        ordering = ["-switched_at"]
        indexes = [
            models.Index(fields=["schema_name", "-switched_at"]),
            models.Index(fields=["to_theme", "-switched_at"]),
        ]

    def __str__(self):
        return f"{self.schema_name}: {self.from_theme or 'none'} -> {self.to_theme}"
