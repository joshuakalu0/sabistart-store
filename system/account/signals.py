from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from system.account.models import Owner


@receiver(post_save, sender=User)
def create_owner_from_user(sender, instance, created, **kwargs):
    """
    Signal to automatically create Owner when Django User is created.
    This runs in the public schema for platform-level users.
    """
    if created:
        try:
            # Create Owner profile for the new User
            Owner.objects.create(
                user=instance,
            )
            print(f"Owner created for user: {instance.username}")

        except Exception as e:
            print(f"Failed to create Owner for user {instance.username}: {e}")