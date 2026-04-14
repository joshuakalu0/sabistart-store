from django.db import models
from public.userauth.models import User


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
        User,
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
        User,
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

    class Meta:
        abstract = True

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
