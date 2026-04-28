import uuid
from django.db import models
from django.contrib.auth.models import User as AuthUser, AbstractUser
from django.core.validators import RegexValidator, EmailValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models import Q
from decimal import Decimal
# import phonenumbers
# from phonenumbers import NumberParseException
from dashboard.settings.models import AuditModel


class Permission(AuditModel):
    """
    Custom permission model for fine-grained access control.
    Extends beyond Django's default permissions for business-specific needs.
    """

    PERMISSION_CATEGORIES = [
        ('product', _('Product Management')),
        ('order', _('Order Management')),
        ('customer', _('Customer Management')),
        ('inventory', _('Inventory Management')),
        ('analytics', _('Analytics & Reports')),
        ('settings', _('System Settings')),
        ('financial', _('Financial Operations')),
        ('marketing', _('Marketing & Promotions')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    codename = models.CharField(max_length=100, unique=True, db_index=True)
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


class Role(AuditModel):
    """
    Role-based access control model.
    Defines user roles with specific permissions and hierarchical structure.
    """

    ROLE_TYPES = [
        ('system', _('System Role')),
        ('business', _('Business Role')),
        ('custom', _('Custom Role')),
    ]

    ROLE_LEVELS = [
        (1, _('Executive')),
        (2, _('Management')),
        (3, _('Supervisor')),
        (4, _('Staff')),
        (5, _('Customer')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    role_type = models.CharField(
        max_length=20, choices=ROLE_TYPES, default='custom', db_index=True)
    level = models.IntegerField(choices=ROLE_LEVELS, default=5, db_index=True)
    permissions = models.ManyToManyField(
        Permission, blank=True, related_name='roles')
    parent_role = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_roles')
    is_system = models.BooleanField(
        default=False, help_text=_("System roles cannot be deleted"))
    is_active = models.BooleanField(default=True, db_index=True)
    max_users = models.PositiveIntegerField(
        null=True, blank=True, help_text=_("Maximum users allowed for this role"))

    class Meta:
        db_table = 'user_roles'
        verbose_name = _('Role')
        verbose_name_plural = _('Roles')
        ordering = ['level', 'name']
        indexes = [
            models.Index(fields=['role_type', 'is_active']),
            models.Index(fields=['level', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} (Level {self.level})"

    def clean(self):
        if self.parent_role and self.parent_role.level >= self.level:
            raise ValidationError(
                _("Parent role must have a higher level (lower number) than child role."))

    def get_all_permissions(self):
        """Get all permissions including inherited from parent roles."""
        permissions = set(self.permissions.filter(is_active=True))
        if self.parent_role:
            permissions.update(self.parent_role.get_all_permissions())
        return permissions


class User(AuditModel):
    """
    Enhanced tenant-isolated user model with comprehensive profile management.
    Supports both staff and customer user types with role-based access control.
    """

    USER_TYPE_CHOICES = [
        ('staff', _('Staff Member')),
        ('customer', _('Customer')),
        # ('vendor', _('Vendor')),
        # ('affiliate', _('Affiliate')),
    ]

    STATUS_CHOICES = [
        ('active', _('Active')),
        ('inactive', _('Inactive')),
        ('suspended', _('Suspended')),
        ('pending', _('Pending Verification')),
        ('banned', _('Banned')),
    ]

    GENDER_CHOICES = [
        ('M', _('Male')),
        ('F', _('Female')),
        ('O', _('Other')),
        ('N', _('Prefer not to say')),
    ]

    # Core Identity
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auth_user = models.OneToOneField(
        AuthUser, on_delete=models.CASCADE, related_name='tenant_profile')
    user_type = models.CharField(
        max_length=20, choices=USER_TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)

    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(
            r'^\+?1?\d{9,15}$', _('Enter a valid phone number'))],
        db_index=True
    )
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)

    # Role & Permissions
    roles = models.ManyToManyField(Role, blank=True, related_name='users')
    custom_permissions = models.ManyToManyField(
        Permission, blank=True, related_name='users')

    # Verification & Security
    email_verified = models.BooleanField(default=False, db_index=True)
    phone_verified = models.BooleanField(default=False, db_index=True)
    two_factor_enabled = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)

    # Business Metrics (for customers)
    total_orders = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'))
    average_order_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'))
    loyalty_points = models.PositiveIntegerField(default=0)
    customer_tier = models.CharField(max_length=20, blank=True, db_index=True)

    # Preferences & Settings
    preferred_language = models.CharField(max_length=10, default='en')
    preferred_currency = models.CharField(max_length=3, default='USD')
    timezone = models.CharField(max_length=50, default='UTC')
    marketing_consent = models.BooleanField(default=False)
    newsletter_subscription = models.BooleanField(default=False)

    # Metadata
    notes = models.TextField(blank=True, help_text=_(
        "Internal notes about this user"))
    tags = models.JSONField(default=list, blank=True,
                            help_text=_("User tags for segmentation"))
    metadata = models.JSONField(
        default=dict, blank=True, help_text=_("Additional user metadata"))

    # Timestamps
    last_activity = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'tenant_users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_type', 'status']),
            models.Index(fields=['email', 'status']),
            models.Index(fields=['customer_tier', 'user_type']),
            models.Index(fields=['last_activity', 'status']),
            models.Index(fields=['total_spent', 'user_type']),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(user_type='staff') | Q(employee_id__isnull=True),
                name='employee_id_only_for_staff'
            ),
            models.CheckConstraint(
                check=Q(salary__gte=0) | Q(salary__isnull=True),
                name='positive_salary'
            ),
            models.CheckConstraint(
                check=Q(total_spent__gte=0),
                name='positive_total_spent'
            ),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    # def clean(self):
    #     # Validate phone number format
    #     if self.phone:
    #         try:
    #             parsed = phonenumbers.parse(self.phone, None)
    #             if not phonenumbers.is_valid_number(parsed):
    #                 raise ValidationError({'phone': _('Invalid phone number format')})
    #         except NumberParseException:
    #             raise ValidationError({'phone': _('Invalid phone number format')})

    #     # Staff-specific validations
    #     if self.user_type == 'staff':
    #         if not self.employee_id:
    #             raise ValidationError({'employee_id': _('Employee ID is required for staff members')})

    #     # Customer-specific validations
    #     if self.user_type == 'customer':
    #         if self.salary is not None:
    #             raise ValidationError({'salary': _('Salary field is not applicable for customers')})

    def save(self, *args, **kwargs):
        self.full_clean()

        # Sync with auth_user
        if self.auth_user:
            self.auth_user.first_name = self.first_name
            self.auth_user.last_name = self.last_name
            self.auth_user.email = self.email
            self.auth_user.is_active = self.status == 'active'
            self.auth_user.save()

        super().save(*args, **kwargs)

    # def get_full_name(self):
    #     """Return the full name of the user."""
    #     return f"{self.first_name} {self.last_name}".strip()

    # def get_short_name(self):
    #     """Return the short name for the user."""
    #     return self.first_name

    def has_permission(self, permission_codename):
        """Check if user has a specific permission."""
        # Check custom permissions
        if self.custom_permissions.filter(codename=permission_codename, is_active=True).exists():
            return True

        # Check role permissions
        for role in self.roles.filter(is_active=True):
            if permission_codename in [p.codename for p in role.get_all_permissions()]:
                return True

        return False

    def get_all_permissions(self):
        """Get all permissions for this user."""
        permissions = set(self.custom_permissions.filter(is_active=True))
        for role in self.roles.filter(is_active=True):
            permissions.update(role.get_all_permissions())
        return permissions

    def is_staff_member(self):
        """Check if user is a staff member."""
        return self.user_type == 'staff'

    def is_customer(self):
        """Check if user is a customer."""
        return self.user_type == 'customer'

    # def update_customer_metrics(self):
    #     """Update customer business metrics."""
    #     if self.user_type == 'customer':
    #         from public.order.models import Order  # Avoid circular import
    #         orders = Order.objects.filter(customer=self, status='completed')
    #         self.total_orders = orders.count()
    #         self.total_spent = sum(order.total_amount for order in orders)
    #         self.average_order_value = self.total_spent / \
    #             self.total_orders if self.total_orders > 0 else Decimal('0.00')
    #         self.save(update_fields=['total_orders',
    #                   'total_spent', 'average_order_value'])

    def can_login(self):
        """Check if user can login."""
        if self.status not in ['active']:
            return False
        if self.account_locked_until and self.account_locked_until > timezone.now():
            return False
        return True

    def lock_account(self, duration_minutes=30):
        """Lock user account for specified duration."""
        self.account_locked_until = timezone.now(
        ) + timezone.timedelta(minutes=duration_minutes)
        self.save(update_fields=['account_locked_until'])

    def unlock_account(self):
        """Unlock user account."""
        self.account_locked_until = None
        self.failed_login_attempts = 0
        self.save(update_fields=[
                  'account_locked_until', 'failed_login_attempts'])


class UserAddress(AuditModel):
    """
    User address model supporting multiple addresses per user.
    Handles both billing and shipping addresses with validation.
    """

    ADDRESS_TYPES = [
        ('billing', _('Billing Address')),
        ('shipping', _('Shipping Address')),
        ('both', _('Billing & Shipping')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='addresses')

    # Address Details
    address_type = models.CharField(
        max_length=20, choices=ADDRESS_TYPES, default='both')
    label = models.CharField(
        max_length=100, help_text=_("e.g., Home, Office, etc."))

    # Contact Information
    full_name = models.CharField(max_length=255)
    company = models.CharField(max_length=255, blank=True)

    # Address Fields
    address_line1 = models.CharField(
        max_length=255, verbose_name=_('Address Line 1'))
    address_line2 = models.CharField(
        max_length=255, blank=True, verbose_name=_('Address Line 2'))
    city = models.CharField(max_length=100)
    state_province = models.CharField(
        max_length=100, verbose_name=_('State/Province'))
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)

    # Geolocation (optional)
    latitude = models.DecimalField(
        max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(
        max_digits=11, decimal_places=8, null=True, blank=True)

    # Preferences
    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    # Delivery Instructions
    delivery_instructions = models.TextField(
        blank=True, help_text=_("Special delivery instructions"))

    class Meta:
        db_table = 'user_addresses'
        verbose_name = _('User Address')
        verbose_name_plural = _('User Addresses')
        ordering = ['-is_default', 'label']
        indexes = [
            models.Index(fields=['user', 'is_default']),
            models.Index(fields=['user', 'address_type']),
            models.Index(fields=['country', 'state_province']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'address_type'],
                condition=Q(is_default=True),
                name='unique_default_address_per_type_per_user'
            )
        ]

    def __str__(self):
        return f"{self.full_name} - {self.label} ({self.city}, {self.country})"

    def save(self, *args, **kwargs):
        # Ensure only one default address per type per user
        if self.is_default:
            UserAddress.objects.filter(
                user=self.user,
                address_type=self.address_type,
                is_default=True
            ).exclude(id=self.id).update(is_default=False)

        super().save(*args, **kwargs)

    def get_formatted_address(self):
        """Return formatted address string."""
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.extend([self.city, self.state_province,
                     self.postal_code, self.country])
        return ', '.join(parts)


class UserSession(AuditModel):
    """
    Track user sessions for security and analytics.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True, db_index=True)

    # Session Details
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    device_type = models.CharField(max_length=50, blank=True)
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)

    # Location (optional)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # Session Status
    is_active = models.BooleanField(default=True, db_index=True)
    last_activity = models.DateTimeField(auto_now=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = 'user_sessions'
        verbose_name = _('User Session')
        verbose_name_plural = _('User Sessions')
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['expires_at', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.ip_address} ({self.last_activity})"

    def is_expired(self):
        """Check if session is expired."""
        return timezone.now() > self.expires_at


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
