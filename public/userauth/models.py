import uuid
from django.db import models
from django.contrib.auth.models import User as Authuser
from django.utils import timezone


class User(models.Model):
    """Tenant-isolated user (lives in each shop's schema)."""

    USER_TYPE_CHOICES = [
        ('staff', 'Staff'),
        ('customer', 'Customer'),
    ]
    user = models.OneToOneField(Authuser, on_delete=models.DO_NOTHING)
    user_type = models.CharField(
        max_length=10, choices=USER_TYPE_CHOICES, db_index=True)

    groups = models.ManyToManyField(
        'auth.Group',
        blank=True,
        related_name='tenant_user_set',
        related_query_name='tenant_user'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        blank=True,
        related_name='tenant_user_set',
        related_query_name='tenant_user'
    )


# class Staff(models.Model):
#     """Staff profile - for internal users."""

#     ROLE_CHOICES = [
#         ('owner', 'Owner'),
#         ('admin', 'Admin'),
#         ('manager', 'Manager'),
#         ('support', 'Support Staff'),
#     ]

#     user = models.OneToOneField(
#         User, on_delete=models.CASCADE, primary_key=True, related_name='staff_profile')
#     role = models.CharField(
#         max_length=20, choices=ROLE_CHOICES, default='support', db_index=True)

#     class Meta:
#         db_table = 'staff'
#         verbose_name = 'Staff'
#         verbose_name_plural = 'Staff'

#     def __str__(self):
#         return f"{self.user.email} - {self.get_role_display()}"


# class Customer(models.Model):
#     """Customer profile - for buyers."""

#     user = models.OneToOneField(
#         User, on_delete=models.CASCADE, primary_key=True, related_name='customer_profile')
#     phone = models.CharField(max_length=20, blank=True)
#     email_verified = models.BooleanField(default=False)

#     class Meta:
#         db_table = 'customers'
#         verbose_name = 'Customer'
#         verbose_name_plural = 'Customers'

#     def __str__(self):
#         return f"{self.user.get_full_name()} ({self.user.email})"


# class CustomerAddress(models.Model):
#     """Customer shipping/billing addresses."""

#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     customer = models.ForeignKey(
#         Customer, on_delete=models.CASCADE, related_name='addresses')

#     full_name = models.CharField(max_length=255)
#     phone = models.CharField(max_length=20)

#     address_line1 = models.CharField(max_length=255)
#     address_line2 = models.CharField(max_length=255, blank=True)
#     city = models.CharField(max_length=100)
#     state = models.CharField(max_length=100)
#     country = models.CharField(max_length=100)
#     postal_code = models.CharField(max_length=20)

#     is_default = models.BooleanField(default=False)

#     created_at = models.DateTimeField(default=timezone.now)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = 'customer_addresses'
#         verbose_name = 'Customer Address'
#         verbose_name_plural = 'Customer Addresses'
#         indexes = [
#             models.Index(fields=['customer', 'is_default']),
#         ]
#         constraints = [
#             models.UniqueConstraint(
#                 fields=['customer'],
#                 condition=models.Q(is_default=True),
#                 name='unique_default_address_per_customer'
#             )
#         ]

#     def __str__(self):
#         return f"{self.full_name} - {self.city}, {self.country}"

#     def save(self, *args, **kwargs):
#         if self.is_default:
#             CustomerAddress.objects.filter(
#                 customer=self.customer,
#                 is_default=True
#             ).exclude(id=self.id).update(is_default=False)
#         super().save(*args, **kwargs)
