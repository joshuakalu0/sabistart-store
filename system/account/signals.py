"""
system/account/signals.py
==========================
Signals for platform-level account events.

These signals run in the PUBLIC schema context.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from system.account.models import PlatformUser


@receiver(post_save, sender=PlatformUser)
def platform_user_post_save(sender, instance, created, **kwargs):
    """
    Signal fired after a PlatformUser is saved.

    On creation:
      - Could trigger a welcome email (handled by the view/service layer)
      - Could create default API keys (handled by the view/service layer)

    NOTE: Do NOT create Shop (tenant) here automatically.
    Shop creation is an explicit user action — the platform user
    must go through the onboarding flow to create their first shop.
    """
    if created:
        # Log creation for audit purposes
        # In production, you might trigger:
        #   - Welcome email via Celery task
        #   - Analytics event
        #   - Default notification preferences
        pass
