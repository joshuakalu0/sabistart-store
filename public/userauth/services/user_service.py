"""
userauth/services/user_service.py
==================================
User management service layer - handles all user-related business logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


from django.db import transaction
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone

from public.userauth.models import TenantUser, Role, Permission

logger = logging.getLogger("userauth.user_service")


# ─────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class UserResult:
    success: bool
    user_id: Optional[str] = None
    error: str = ""
    error_code: str = ""
    field_errors: dict = field(default_factory=dict)


@dataclass
class UserListResult:
    users: list
    total_count: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


# ─────────────────────────────────────────────────────────────
# USER CRUD OPERATIONS
# ─────────────────────────────────────────────────────────────

def get_users(
    user_type: str = "",
    status: str = "",
    role_id: str = "",
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "-created_at"
) -> UserListResult:
    """Get paginated list of users with filters."""
    qs = TenantUser.objects.select_related('user').prefetch_related('roles')

    if user_type:
        qs = qs.filter(user_type=user_type)
    if status:
        qs = qs.filter(status=status)
    if role_id:
        qs = qs.filter(roles__id=role_id)
    if search:
        qs = qs.filter(
            Q(user__email__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(phone__icontains=search)
        )

    qs = qs.order_by(sort_by)
    total_count = qs.count()
    offset = (page - 1) * page_size
    users = list(qs[offset:offset + page_size])

    return UserListResult(
        users=users,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total_count,
        has_prev=page > 1
    )


def get_user_by_id(user_id: str) -> Optional[TenantUser]:
    """Get user by ID."""
    try:
        return TenantUser.objects.select_related('user').prefetch_related('roles', 'custom_permissions').get(id=user_id)
    except TenantUser.DoesNotExist:
        return None


def get_user_by_email(email: str) -> Optional[TenantUser]:
    """Get user by email."""
    try:
        return TenantUser.objects.select_related('user').get(user__email=email.strip().lower())
    except TenantUser.DoesNotExist:
        return None


@transaction.atomic
def create_user(
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    user_type: str = "customer",
    phone: str = "",
    employee_id: str = "",
    role_ids: list = None,
    created_by: TenantUser = None,
    **kwargs
) -> UserResult:
    """Create a new user with auth user and tenant profile."""
    email = email.strip().lower()
    field_errors = {}

    # Validation
    if not email:
        field_errors["email"] = "Email is required"
    elif TenantUser.objects.filter(email=email).exists():
        field_errors["email"] = "Email already exists"

    if not password or len(password) < 8:
        field_errors["password"] = "Password must be at least 8 characters"

    if user_type == 'staff' and not employee_id:
        field_errors["employee_id"] = "Employee ID is required for staff"

    if field_errors:
        return UserResult(
            success=False,
            error="Validation failed",
            error_code="VALIDATION_ERROR",
            field_errors=field_errors
        )

    try:
        # Create auth user
        auth_user = TenantUser.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            is_active=kwargs.get('status', 'active') == 'active'
        )

        # Create tenant user profile
        user = TenantUser.objects.create(
            user=auth_user,
            user_type=user_type,
            phone=phone.strip(),
            status=kwargs.get('status', 'pending'),
            date_of_birth=kwargs.get('date_of_birth'),
            gender=kwargs.get('gender', ''),
            email_verified=kwargs.get('email_verified', False),
            phone_verified=kwargs.get('phone_verified', False),
            marketing_consent=kwargs.get('marketing_consent', False),
            newsletter_subscription=kwargs.get(
                'newsletter_subscription', False),
            notes=kwargs.get('notes', ''),
            created_by=created_by
        )

        # Assign roles
        if role_ids:
            roles = Role.objects.filter(id__in=role_ids, is_active=True)
            user.roles.set(roles)

        logger.info(f"User created: {email} (id={user.id})")

        return UserResult(success=True, user_id=str(user.id))

    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return UserResult(
            success=False,
            error=f"Error creating user: {str(e)}",
            error_code="CREATE_ERROR"
        )


@transaction.atomic
def update_user(
    user_id: str,
    data: dict,
    updated_by: TenantUser = None
) -> UserResult:
    """Update user details."""
    try:
        user = TenantUser.objects.select_related('user').get(id=user_id)
    except TenantUser.DoesNotExist:
        return UserResult(success=False, error="User not found", error_code="NOT_FOUND")

    try:
        # Update auth user fields
        auth_user = user.user
        if 'email' in data:
            email = data['email'].strip().lower()
            if TenantUser.objects.filter(email=email).exclude(id=auth_user.id).exists():
                return UserResult(
                    success=False,
                    error="Email already exists",
                    error_code="DUPLICATE_EMAIL",
                    field_errors={"email": "Email already exists"}
                )
            auth_user.email = email
            auth_user.username = email

        if 'first_name' in data:
            auth_user.first_name = data['first_name'].strip()
        if 'last_name' in data:
            auth_user.last_name = data['last_name'].strip()
        if 'status' in data:
            auth_user.is_active = data['status'] == 'active'

        auth_user.save()

        # Update tenant user fields
        allowed_fields = {
            'user_type', 'status', 'phone', 'date_of_birth', 'gender',
            'email_verified', 'phone_verified', 'two_factor_enabled',
            'marketing_consent', 'newsletter_subscription', 'notes',
            'preferred_language', 'preferred_currency', 'timezone_name',
            'customer_tier', 'loyalty_points'
        }

        update_fields = []
        for field_name, value in data.items():
            if field_name in allowed_fields:
                setattr(user, field_name, value)
                update_fields.append(field_name)

        if update_fields:
            user.updated_by = updated_by
            update_fields.extend(['updated_by', 'updated_at'])
            user.save(update_fields=update_fields)

        # Update roles
        if 'role_ids' in data:
            roles = Role.objects.filter(
                id__in=data['role_ids'], is_active=True)
            user.roles.set(roles)

        logger.info(f"User updated: {user.user.email} (id={user.id})")

        return UserResult(success=True, user_id=str(user.id))

    except Exception as e:
        logger.error(f"Error updating user: {e}")
        return UserResult(
            success=False,
            error=f"Error updating user: {str(e)}",
            error_code="UPDATE_ERROR"
        )


def deactivate_user(
    user_id: str,
    reason: str = "",
    deactivated_by: TenantUser = None
) -> UserResult:
    """Deactivate a user account."""
    try:
        user = TenantUser.objects.select_related('user').get(id=user_id)
        user.status = 'inactive'
        user.user.is_active = False
        user.notes = f"{user.notes}\n\nDeactivated: {reason}" if reason else user.notes
        user.updated_by = deactivated_by
        user.save(update_fields=['status', 'notes',
                  'updated_by', 'updated_at'])
        user.user.save(update_fields=['is_active'])

        logger.info(f"User deactivated: {user.user.email} (id={user.id})")
        return UserResult(success=True, user_id=str(user.id))

    except TenantUser.DoesNotExist:
        return UserResult(success=False, error="User not found", error_code="NOT_FOUND")
    except Exception as e:
        logger.error(f"Error deactivating user: {e}")
        return UserResult(success=False, error=str(e), error_code="DEACTIVATE_ERROR")


def reactivate_user(
    user_id: str,
    reactivated_by: TenantUser = None
) -> UserResult:
    """Reactivate a user account."""
    try:
        user = TenantUser.objects.select_related('user').get(id=user_id)
        user.status = 'active'
        user.user.is_active = True
        user.updated_by = reactivated_by
        user.save(update_fields=['status', 'updated_by', 'updated_at'])
        user.user.save(update_fields=['is_active'])

        logger.info(f"User reactivated: {user.user.email} (id={user.id})")
        return UserResult(success=True, user_id=str(user.id))

    except TenantUser.DoesNotExist:
        return UserResult(success=False, error="User not found", error_code="NOT_FOUND")
    except Exception as e:
        logger.error(f"Error reactivating user: {e}")
        return UserResult(success=False, error=str(e), error_code="REACTIVATE_ERROR")


# ─────────────────────────────────────────────────────────────
# USER STATISTICS & ANALYTICS
# ─────────────────────────────────────────────────────────────

def get_user_statistics() -> dict:
    """Get user statistics for dashboard."""
    total_users = TenantUser.objects.count()
    active_users = TenantUser.objects.filter(status='active').count()
    staff_count = TenantUser.objects.filter(user_type='staff').count()
    customer_count = TenantUser.objects.filter(user_type='customer').count()

    # Recent registrations
    from datetime import timedelta
    last_30_days = timezone.now() - timedelta(days=30)
    recent_users = TenantUser.objects.filter(
        created_at__gte=last_30_days).count()

    # Customer metrics
    customer_stats = TenantUser.objects.filter(user_type='customer').aggregate(
        total_spent=Sum('total_spent'),
        avg_spent=Avg('total_spent'),
        total_orders=Sum('total_orders')
    )

    return {
        'total_users': total_users,
        'active_users': active_users,
        'staff_count': staff_count,
        'customer_count': customer_count,
        'recent_users': recent_users,
        'customer_total_spent': customer_stats['total_spent'] or Decimal('0.00'),
        'customer_avg_spent': customer_stats['avg_spent'] or Decimal('0.00'),
        'customer_total_orders': customer_stats['total_orders'] or 0,
    }


# ─────────────────────────────────────────────────────────────
# ROLE & PERMISSION MANAGEMENT
# ─────────────────────────────────────────────────────────────

def get_roles(include_inactive: bool = False) -> list:
    """Get all roles."""
    qs = Role.objects.prefetch_related('role_permissions__permission')
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return list(qs.order_by('sort_order', 'name'))


def get_permissions() -> list:
    """Get all permissions."""
    return list(Permission.objects.filter(is_active=True).order_by('category', 'name'))


@transaction.atomic
def create_role(
    name: str,
    description: str = "",
    role_type: str = "custom",
    level: int = 5,
    permission_ids: list = None,
    created_by: TenantUser = None
) -> UserResult:
    """Create a new role."""
    from django.utils.text import slugify

    slug = slugify(name)
    if Role.objects.filter(slug=slug).exists():
        return UserResult(
            success=False,
            error=f"Role with name '{name}' already exists",
            error_code="DUPLICATE_ROLE"
        )

    try:
        role = Role.objects.create(
            name=name,
            slug=slug,
            description=description,
            role_type=role_type,
            level=level,
            is_system=False,
            created_by=created_by
        )

        # Assign permissions
        if permission_ids:
            from public.userauth.models import RolePermission
            permissions = Permission.objects.filter(
                id__in=permission_ids, is_active=True)
            for perm in permissions:
                RolePermission.objects.create(
                    role=role,
                    permission=perm,
                    granted_by=created_by.id if created_by else None
                )

        logger.info(f"Role created: {name} (id={role.id})")
        return UserResult(success=True, user_id=str(role.id))

    except Exception as e:
        logger.error(f"Error creating role: {e}")
        return UserResult(success=False, error=str(e), error_code="CREATE_ERROR")


# ─────────────────────────────────────────────────────────────
# SESSION & ACTIVITY MANAGEMENT
# ─────────────────────────────────────────────────────────────

def get_user_active_sessions(user: TenantUser) -> list:
    """Get active sessions for a user."""
    # Placeholder - implement when session model is available
    return []


def terminate_user_sessions(user: TenantUser) -> int:
    """Terminate all active sessions for a user."""
    # Placeholder - implement when session model is available
    return 0


def get_user_login_history(user: TenantUser, limit: int = 20) -> list:
    """Get login history for a user."""
    from public.userauth.models import LoginAuditLog
    return list(LoginAuditLog.objects.filter(user=user).order_by('-created_at')[:limit])
