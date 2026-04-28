"""
system/account/admin.py
========================
Django admin registration for platform-level models.

PlatformUser is the AUTH_USER_MODEL — registered with a custom
UserAdmin that replaces the default Django UserAdmin.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from system.account.models import (
    PlatformUser,
    PlatformEmailVerificationToken,
    PlatformPasswordResetToken,
    PlatformAPIKey,
    PlatformLoginAuditLog,
)


@admin.register(PlatformUser)
class PlatformUserAdmin(BaseUserAdmin):
    """
    Admin for PlatformUser — replaces Django's default UserAdmin.
    Uses email as the primary identifier (no username field).
    """

    ordering = ["-created_at"]
    list_display = [
        "email", "first_name", "last_name",
        "account_status", "is_verified", "is_platform_admin",
        "created_at",
    ]
    list_filter = [
        "account_status", "is_verified", "is_platform_admin",
        "is_staff", "is_active",
    ]
    search_fields = ["email", "first_name", "last_name", "phone"]
    readonly_fields = ["id", "created_at",
                       "updated_at", "last_login_at", "last_login_ip"]

    fieldsets = (
        (None, {
            "fields": ("id", "email", "password"),
        }),
        (_("Personal info"), {
            "fields": ("first_name", "last_name", "phone", "avatar_url"),
        }),
        (_("Account status"), {
            "fields": (
                "account_status", "is_verified", "verified_at",
                "is_active", "is_staff", "is_platform_admin",
            ),
        }),
        (_("Security"), {
            "fields": (
                "totp_enabled", "totp_confirmed_at",
                "failed_login_count", "locked_until",
                "force_password_reset", "password_changed_at",
            ),
            "classes": ("collapse",),
        }),
        (_("OAuth"), {
            "fields": ("google_id", "facebook_id", "github_id"),
            "classes": ("collapse",),
        }),
        (_("Preferences"), {
            "fields": ("locale", "timezone", "email_marketing"),
            "classes": ("collapse",),
        }),
        (_("Activity"), {
            "fields": ("last_login_at", "last_login_ip", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
        (_("Permissions"), {
            "fields": ("is_superuser", "groups", "user_permissions"),
            "classes": ("collapse",),
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email", "first_name", "last_name",
                "password1", "password2",
                "account_status", "is_staff", "is_platform_admin",
            ),
        }),
    )

    # PlatformUser uses email, not username
    USERNAME_FIELD = "email"


@admin.register(PlatformEmailVerificationToken)
class PlatformEmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "purpose", "is_used",
                    "is_expired", "expires_at", "created_at"]
    list_filter = ["purpose", "is_used"]
    search_fields = ["user__email"]
    readonly_fields = ["id", "token", "created_at", "used_at"]

    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True


@admin.register(PlatformPasswordResetToken)
class PlatformPasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "is_used", "is_expired",
                    "request_ip", "expires_at", "created_at"]
    list_filter = ["is_used"]
    search_fields = ["user__email", "request_ip"]
    readonly_fields = ["id", "token", "created_at", "used_at"]

    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True


@admin.register(PlatformAPIKey)
class PlatformAPIKeyAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "key_type", "key_prefix",
                    "is_active", "last_used_at", "created_at"]
    list_filter = ["key_type", "is_active"]
    search_fields = ["user__email", "name", "key_prefix"]
    readonly_fields = ["id", "key_hash", "key_prefix",
                       "created_at", "last_used_at", "revoked_at"]


@admin.register(PlatformLoginAuditLog)
class PlatformLoginAuditLogAdmin(admin.ModelAdmin):
    list_display = ["attempted_email", "result",
                    "ip_address", "is_suspicious", "created_at"]
    list_filter = ["result", "is_suspicious"]
    search_fields = ["attempted_email", "ip_address"]
    readonly_fields = [f.name for f in PlatformLoginAuditLog._meta.get_fields()
                       if hasattr(f, 'name')]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
