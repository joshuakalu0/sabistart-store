from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from system.theme_marketplace.models import TenantActiveTheme, TenantThemeAccess
from system.theme_marketplace.services import (
    clear_active_theme_cache,
    deactivate_theme_for_schema,
)


@receiver(post_save, sender=TenantActiveTheme)
def invalidate_active_theme_cache(sender, instance: TenantActiveTheme, **kwargs):
    clear_active_theme_cache(instance.schema_name)


@receiver(post_save, sender=TenantThemeAccess)
def fallback_if_active_access_is_revoked(sender, instance: TenantThemeAccess, **kwargs):
    if instance.is_active:
        return
    active = TenantActiveTheme.objects.filter(schema_name=instance.schema_name, theme=instance.theme).first()
    if active is None:
        return
    deactivate_theme_for_schema(instance.schema_name, reason="access_revoked")
