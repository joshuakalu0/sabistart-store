# from django.db.models.signals import post_save, pre_delete
# from django.dispatch import receiver
# from django.contrib.auth.models import User as AuthUser
# from django.utils import timezone
# from .models import User, Role


# @receiver(post_save, sender=AuthUser)
# def create_or_update_tenant_user(sender, instance, created, **kwargs):
#     """
#     Signal to create or update tenant user when Django auth user is created/updated.
#     Ensures synchronization between auth user and tenant user profiles.
#     """
#     if created:
#         # Create tenant user for new auth user
#         tenant_user = User.objects.create(
#             auth_user=instance,
#             first_name=instance.first_name or '',
#             last_name=instance.last_name or '',
#             email=instance.email or '',
#             user_type='customer',  # Default to customer
#             status='pending' if not instance.is_active else 'active',
#         )

#         # Assign default customer role
#         try:
#             customer_role = Role.objects.get(slug='customer')
#             tenant_user.roles.add(customer_role)
#         except Role.DoesNotExist:
#             pass
#     else:
#         # Update existing tenant user
#         try:
#             tenant_user = User.objects.get(auth_user=instance)
#             tenant_user.first_name = instance.first_name or tenant_user.first_name
#             tenant_user.last_name = instance.last_name or tenant_user.last_name
#             tenant_user.email = instance.email or tenant_user.email
#             tenant_user.status = 'active' if instance.is_active else 'inactive'
#             tenant_user.save()
#         except User.DoesNotExist:
#             pass


# @receiver(pre_delete, sender=AuthUser)
# def handle_auth_user_deletion(sender, instance, **kwargs):
#     """
#     Signal to handle auth user deletion.
#     Ensures proper cleanup of related tenant user data.
#     """
#     try:
#         tenant_user = User.objects.get(auth_user=instance)
#         # Mark as inactive instead of deleting to preserve data integrity
#         tenant_user.status = 'inactive'
#         tenant_user.save()
#     except User.DoesNotExist:
#         pass


# @receiver(post_save, sender=User)
# def update_customer_metrics_on_user_save(sender, instance, created, **kwargs):
#     """
#     Signal to update customer metrics when user is saved.
#     Only applies to customer user types.
#     """
#     if instance.user_type == 'customer' and not created:
#         # Update last activity
#         instance.last_activity = timezone.now()
#         # Note: Actual metrics update should be done via separate task
#         # to avoid performance issues during user save operations
