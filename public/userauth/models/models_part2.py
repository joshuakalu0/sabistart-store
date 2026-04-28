"""
accounts/models_part2.py
=========================
APP 2 — Accounts Domain | Part 2 of 3

PART 2 — Staff, Roles & Permissions (TENANT schema)
  Section 9  — Permission definitions
  Section 10 — Roles
  Section 11 — Role permissions
  Section 12 — StoreStaff (tenant membership)
  Section 13 — Staff invitations
  Section 14 — Staff activity log
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dashboard.settings.models import AuditModel, MixIdAndTimeModel, IduuidModel
from public.userauth.permission_registry import (
    PERMISSION_CODENAMES as REGISTRY_PERMISSION_CODENAMES,
    PERMISSION_CATEGORY_CHOICES,
    iter_permission_codenames,
)
from .tenant_user import TenantUser


# ─────────────────────────────────────────────────────────────
# SECTION 9 — PERMISSION DEFINITIONS  (tenant schema)
# ─────────────────────────────────────────────────────────────

PERMISSION_CODENAMES = REGISTRY_PERMISSION_CODENAMES


class Permission(AuditModel, IduuidModel):
    """
    Custom permission model for fine-grained access control.
    Extends beyond Django's default permissions for business-specific needs.
    """

    PERMISSION_CATEGORIES = PERMISSION_CATEGORY_CHOICES

    name = models.CharField(max_length=100, unique=True, db_index=True)
    codename = models.CharField(max_length=100, unique=True, db_index=True,
                                help_text="Dot-separated e.g. orders.refund")
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=20, choices=PERMISSION_CATEGORIES, db_index=True)
    is_system = models.BooleanField(default=False, help_text=_(
        "System permissions cannot be deleted"))
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'custom_permissions'
        verbose_name = _('Permission')
        verbose_name_plural = _('Permissions')
        ordering = ['category', 'name']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['codename', 'is_active']),
        ]

    def __str__(self):
        return f"{self.get_category_display()}: {self.name}"

    @classmethod
    def get_category(cls, codename: str) -> str:
        return codename.split(".")[0] if "." in codename else codename

    def save(self, *args, **kwargs):
        self.category = self.get_category(self.codename)
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# SECTION 10 — ROLES  (tenant schema)
# ─────────────────────────────────────────────────────────────

class Role(AuditModel, IduuidModel):
    """
    A named set of permissions scoped to a tenant store.

    System roles (is_system=True) are seeded automatically and
    cannot be deleted. Tenants can create unlimited custom roles.

    Built-in system roles:
      Owner       — all permissions (cannot be restricted)
      Admin       — all non-billing permissions
      Manager     — orders + products + inventory + customers + analytics
      Fulfillment — orders.view + orders.fulfil only
      Support     — orders.view + customers.view + edit
      Analyst     — analytics.view + analytics.export only
    """

    class SystemRole(models.TextChoices):
        OWNER = "owner",       _("Owner")
        ADMIN = "admin",       _("Admin")
        MANAGER = "manager",     _("Manager")
        FULFILLMENT = "fulfillment", _("Fulfillment")
        SUPPORT = "support",     _("Support")
        ANALYST = "analyst",     _("Analyst")
        CUSTOM = "custom",     _("Custom")

    ROLE_TYPES = [
        ('system', _('System Role')),
        ('business', _('Business Role')),
        ('custom', _('Custom Role')),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, db_index=True)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False,
                                    help_text="System roles cannot be deleted")
    is_active = models.BooleanField(default=True, db_index=True)
    system_slug = models.CharField(max_length=20, blank=True,
                                   choices=SystemRole.choices,
                                   help_text="If set, this is a built-in system role")
    role_type = models.CharField(
        max_length=20, choices=ROLE_TYPES, default='custom', db_index=True)
    color = models.CharField(max_length=7, default="#4c4c88",
                             help_text="Hex color for UI display")
    sort_order = models.PositiveSmallIntegerField(default=100)
    max_users = models.PositiveIntegerField(
        null=True, blank=True, help_text=_("Maximum users allowed for this role"))

    # Cached permission count for UI display
    _permission_count = models.PositiveSmallIntegerField(default=0,
                                                         db_column="permission_count")

    class Meta:
        app_label = "userauth"
        ordering = ["sort_order", "name"]
        unique_together = [("slug",)]

    def __str__(self) -> str:
        return self.name

    @property
    def is_owner_role(self) -> bool:
        return self.system_slug == self.SystemRole.OWNER

    def get_permissions(self) -> list[str]:
        """Return list of permission codenames for this role."""
        if self.is_owner_role:
            return list(iter_permission_codenames())
        return list(
            self.role_permissions.values_list(
                "permission__codename", flat=True)
        )

    def has_permission(self, codename: str) -> bool:
        return self.role_permissions.filter(
            permission__codename=codename
        ).exists()

    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValueError(f"System role '{self.name}' cannot be deleted.")
        super().delete(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# SECTION 11 — ROLE PERMISSIONS  (tenant schema)
# ─────────────────────────────────────────────────────────────

class RolePermission(MixIdAndTimeModel):
    """Junction: maps a Role to a specific Permission."""

    role = models.ForeignKey(Role, on_delete=models.CASCADE,
                             related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE,
                                   related_name="role_permissions")
    granted_by = models.UUIDField(null=True, blank=True,
                                  help_text="User UUID who added this permission")

    class Meta:
        app_label = "userauth"
        unique_together = [("role", "permission")]
        verbose_name = "Role Permission"

    def __str__(self) -> str:
        return f"{self.role.name} → {self.permission.codename}"


# ─────────────────────────────────────────────────────────────
# SECTION 12 — STORE STAFF  (tenant schema)
# ─────────────────────────────────────────────────────────────

class StoreStaff(AuditModel):
    """
    Links a platform User to a tenant store with a Role.

    Lives in the TENANT schema — each store has its own staff table.
    Supports per-staff permission overrides (additions / removals) on
    top of the base role.

    One User can be staff on multiple tenant stores simultaneously
    (one StoreStaff row per store's schema).
    """

    class StaffStatus(models.TextChoices):
        ACTIVE = "ACTIVE",    _("Active")
        INACTIVE = "INACTIVE",  _("Inactive — login disabled for this store")
        SUSPENDED = "SUSPENDED", _("Suspended")

    # ── Identity ──────────────────────────────────────────────────────
    user = models.ForeignKey(
        TenantUser,
        on_delete=models.CASCADE,
        related_name="staff_memberships",
    )
    role = models.ForeignKey(
        "Role",
        on_delete=models.PROTECT,
        related_name="staff_members",
    )

    # ── Status ────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=12,
        choices=StaffStatus.choices,
        default=StaffStatus.ACTIVE,
        db_index=True,
    )

    # ── Permission overrides (on top of role) ─────────────────────────
    extra_permissions = models.JSONField(
        default=list,
        help_text=_("Permission codenames ADDED beyond the role."),
    )
    removed_permissions = models.JSONField(
        default=list,
        help_text=_("Permission codenames REMOVED from the role."),
    )

    # ── Access restrictions ───────────────────────────────────────────
    allowed_ips = models.JSONField(
        default=list,
        blank=True,
        help_text=_(
            "Restrict staff to specific IP ranges. Empty = no restriction."),
    )
    # Store-level 2FA enforcement. When True the staff member must have
    # User.two_factor_enabled=True before they can log in to this store.
    require_2fa = models.BooleanField(
        default=False,
        help_text=_(
            "Force this staff member to enable 2FA before accessing this store."),
    )

    class Meta:
        app_label = "userauth"
        verbose_name = "Store Staff"
        verbose_name_plural = "Store Staff"
        # one staff record per user per tenant schema
        unique_together = [("user_id",)]
        indexes = [
            models.Index(fields=["user_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} — {self.role.name}"

    @property
    def email(self) -> str:
        """Access user email."""
        return self.user.email if self.user else ""

    @property
    def full_name(self) -> str:
        """Access user full name."""
        return self.user.get_full_name() if self.user else ""

    @property
    def is_owner(self) -> bool:
        return self.role.is_owner_role

    @property
    def is_active(self) -> bool:
        return self.status == self.StaffStatus.ACTIVE

    def get_effective_permissions(self) -> set[str]:
        """
        Compute the full permission set for this staff member:
        Role permissions + extra_permissions - removed_permissions.
        """
        role_perms = set(self.role.get_permissions())
        if self.role.is_owner_role:
            # Owner always gets ALL permissions
            return set(iter_permission_codenames())
        effective = (role_perms | set(self.extra_permissions)) - \
            set(self.removed_permissions)
        return effective

    def has_permission(self, codename: str) -> bool:
        if self.role.is_owner_role:
            return True
        if self.status != self.StaffStatus.ACTIVE:
            return False
        return codename in self.get_effective_permissions()

    def has_any_permission(self, *codenames: str) -> bool:
        perms = self.get_effective_permissions()
        return any(c in perms for c in codenames)

    def grant_permission(self, codename: str, granted_by_id: uuid.UUID = None) -> None:
        """Add an extra permission override."""
        if codename not in self.extra_permissions:
            self.extra_permissions = list(self.extra_permissions) + [codename]
        # If it was in removed, un-remove it
        if codename in self.removed_permissions:
            self.removed_permissions = [
                p for p in self.removed_permissions if p != codename]
        self.save(update_fields=["extra_permissions",
                  "removed_permissions", "updated_at"])

    def revoke_permission(self, codename: str) -> None:
        """Remove a permission override."""
        if codename not in self.removed_permissions:
            self.removed_permissions = list(
                self.removed_permissions) + [codename]
        if codename in self.extra_permissions:
            self.extra_permissions = [
                p for p in self.extra_permissions if p != codename]
        self.save(update_fields=["extra_permissions",
                  "removed_permissions", "updated_at"])

    # Removed update_cached_fields - fields are accessed via user FK directly

 # ─────────────────────────────────────────────────────────────
 # SECTION 14 — STAFF ACTIVITY LOG  (tenant schema)
# ─────────────────────────────────────────────────────────────


class StaffActivityLog(MixIdAndTimeModel):
    """
    Append-only record of sensitive staff actions within a tenant store.
    Used for the staff audit trail in the admin panel.

    Complements the platform-wide AuditLog (App 13) —
    this is focused on store-level staff actions.
    """

    class ActionCategory(models.TextChoices):
        AUTH = "AUTH",         _("Authentication")
        ORDER = "ORDER",        _("Order management")
        PRODUCT = "PRODUCT",      _("Product management")
        CUSTOMER = "CUSTOMER",     _("Customer management")
        PAYMENT = "PAYMENT",      _("Payment/payout")
        SETTINGS = "SETTINGS",     _("Store settings")
        STAFF = "STAFF",        _("Staff management")
        THEME = "THEME",        _("Theme/customisation")
        INVENTORY = "INVENTORY",    _("Inventory")
        DISCOUNT = "DISCOUNT",     _("Discount/pricing")

    staff = models.ForeignKey(StoreStaff, db_index=True,
                              on_delete=models.DO_NOTHING,
                              help_text="StoreStaff.id who performed the action")
    user = models.ForeignKey(TenantUser,
                             on_delete=models.DO_NOTHING,
                             db_index=True,
                             help_text="TenantUser.id (denormalised for quick lookup)")
    staff_email = models.EmailField(db_index=True)
    staff_name = models.CharField(max_length=200)

    category = models.CharField(max_length=12, choices=ActionCategory.choices,
                                db_index=True)
    action = models.CharField(max_length=200,
                              help_text="Short description e.g. 'order.cancelled'")
    description = models.TextField(blank=True,
                                   help_text="Human-readable sentence describing what happened")

    # The object that was acted upon
    target_type = models.CharField(max_length=50, blank=True,
                                   help_text="e.g. 'order', 'product', 'customer'")
    target_id = models.CharField(max_length=100, blank=True)
    target_label = models.CharField(max_length=200, blank=True,
                                    help_text="e.g. Order #1001, Product 'Blue Widget'")

    # Before/after snapshot for sensitive changes
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)

    # Request metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        app_label = "userauth"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["staff_id", "created_at"]),
            models.Index(fields=["category", "created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.staff_email} — {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        """Immutable — block updates."""
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValueError("StaffActivityLog is immutable.")
        super().save(*args, **kwargs)
