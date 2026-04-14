from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from public.userauth.models import User as TenantUser


@receiver(post_save, sender=User)
def create_tenant_user_from_django_user(sender, instance, created, **kwargs):
    """
    Signal to automatically create tenant User when Django User is created.
    This runs in tenant schema for store-level users.
    """
    if created:
        try:
            # Only create tenant user if we're in a tenant schema
            from django_tenants.utils import tenant_context
            from django.db import connection

            # Check if we're in a tenant schema (not public)
            if hasattr(connection, 'tenant') and connection.tenant.schema_name != 'public':
                # Create tenant User profile
                TenantUser.objects.create(
                    user=instance
                )
                print(f"Tenant user created for: {instance.username}")

        except Exception as e:
            print(f"Failed to create tenant user for {instance.username}: {e}")