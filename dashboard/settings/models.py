from django.conf import settings
from django.db import models
import uuid
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from public.userauth.models.tenant_user import TenantUser

# ─────────────────────────────────────────────────────────────
# ABSTRACT BASES
# ─────────────────────────────────────────────────────────────


class TimestampedModel(models.Model):
    """Stamps created_at / updated_at on every concrete model."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class IduuidModel(models.Model):
    """Stamps created_at / updated_at on every concrete model."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class MixIdAndTimeModel(IduuidModel, TimestampedModel):
    class Meta:
        abstract = True


class ActivatableModel(models.Model):
    """
    Adds is_active, starts_at, ends_at — the shared scheduling
    pattern for promotions, discount codes, flash sales, etc.
    """
    is_active = models.BooleanField(_("Active"), default=True, db_index=True)
    starts_at = models.DateTimeField(
        _("Starts At"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            "Leave blank to be active immediately when is_active=True."),
    )
    ends_at = models.DateTimeField(
        _("Ends At"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Leave blank for no expiry."),
    )

    class Meta:
        abstract = True

    @property
    def is_currently_active(self) -> bool:
        """True if active flag is set AND within optional date window."""
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


# ============================================
# AUDITING & TRACKING
# ============================================

class AuditModel(models.Model):
    """
    Abstract base model that provides audit fields and tracking capabilities.

    Tracks:
    - Who created the record
    - When the record was created
    - Who last modified the record
    - When the record was last modified

    Usage:
        class MyModel(AuditModel):
            # Your fields here
            pass
    """
    created_by = models.ForeignKey(
        TenantUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
        help_text="User who created this record"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Date and time when this record was created"
    )
    updated_by = models.ForeignKey(
        TenantUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated',
        help_text="User who last modified this record"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        help_text="Date and time when this record was last modified"
    )
    deleted_by = models.ForeignKey(
        TenantUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_deleted',
        help_text="User who deleted this record"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Date and time when this record was deleted"
    )
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this record is soft-deleted"
    )

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        """
        Override delete method to perform soft delete instead of hard delete.

        Usage:
            instance.delete()  # Soft delete
            instance.delete(hard=True)  # Hard delete
        """
        if kwargs.pop('hard', False):
            super().delete(*args, **kwargs)
        else:
            self.is_deleted = True
            self.deleted_at = timezone.now()

            if 'deleted_by' in kwargs:
                self.deleted_by = kwargs.pop('deleted_by')
            self.save()

    def save(self, *args, **kwargs):
        """
        Override save method to automatically set updated_by field
        if user is provided in kwargs.

        Usage:
            instance.save(updated_by=request.user)
            instance.save(created_by=request.user, updated_by=request.user)
        """
        # Handle created_by on first save
        if not self.pk:
            if 'created_by' in kwargs:
                self.created_by = kwargs.pop('created_by')

        # Handle updated_by on every save
        if 'updated_by' in kwargs:
            self.updated_by = kwargs.pop('updated_by')

        super().save(*args, **kwargs)
