"""
accounts/utils/staff_service.py
=================================
Staff and customer management service layer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone

logger = logging.getLogger("accounts.staff_service")


# ─────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class StaffActionResult:
    success: bool
    error: str = ""
    error_code: str = ""


@dataclass
class InviteResult:
    success: bool
    invitation_id: Optional[str] = None
    email: str = ""
    role_name: str = ""
    expires_at: str = ""
    error: str = ""
    error_code: str = ""


# ─────────────────────────────────────────────────────────────
# PERMISSION CHECK DECORATOR
# ─────────────────────────────────────────────────────────────

def require_permission(codename: str):
    """
    Decorator for view functions that checks StoreStaff permission.

    Usage:
        @login_required
        @require_permission("staff.invite")
        def invite_staff(request): ...
    """
    from functools import wraps
    from django.http import HttpResponseForbidden

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            staff = get_current_staff(request)
            if not staff:
                return HttpResponseForbidden("Staff record not found.")
            if not staff.has_permission(codename):
                return HttpResponseForbidden(
                    f"You don't have permission to do this. Required: {codename}"
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def get_current_staff(request):
    """Get the StoreStaff record for the currently logged-in user."""
    from accounts.models import StoreStaff
    if not request.user.is_authenticated:
        return None
    try:
        return StoreStaff.objects.select_related("role").get(
            user_id=request.user.id,
            status=StoreStaff.StaffStatus.ACTIVE,
        )
    except StoreStaff.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────
# STAFF MANAGEMENT
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def invite_staff_member(
    email: str,
    role_id: str,
    invited_by_staff,
    personal_message: str = "",
) -> InviteResult:
    """Send an invitation to join the store as staff."""
    from accounts.models import StaffInvitation, Role, StoreStaff

    email = email.strip().lower()

    # Check if already a staff member
    if StoreStaff.objects.filter(email=email).exists():
        return InviteResult(
            success=False,
            error=f"{email} is already a staff member of this store.",
            error_code="ALREADY_STAFF",
        )

    try:
        role = Role.objects.get(id=role_id)
    except Role.DoesNotExist:
        return InviteResult(success=False, error="Role not found.", error_code="ROLE_NOT_FOUND")

    # Cannot invite someone with a higher role than yourself
    if not invited_by_staff.is_owner and role.is_owner_role:
        return InviteResult(
            success=False,
            error="Only owners can invite other owners.",
            error_code="INSUFFICIENT_PERMISSIONS",
        )

    invitation = StaffInvitation.create(
        email=email,
        role=role,
        invited_by_staff=invited_by_staff,
        personal_message=personal_message,
    )

    # Send invitation email
    _send_staff_invitation_email(invitation)

    logger.info("Staff invitation sent to %s for role %s", email, role.name)

    return InviteResult(
        success=True,
        invitation_id=str(invitation.id),
        email=email,
        role_name=role.name,
        expires_at=invitation.expires_at.isoformat(),
    )


def accept_staff_invitation(token: str, user) -> StaffActionResult:
    """Accept a staff invitation with the given token."""
    from accounts.models import StaffInvitation

    try:
        invitation = StaffInvitation.objects.select_related("role").get(token=token)
    except StaffInvitation.DoesNotExist:
        return StaffActionResult(success=False, error="Invalid invitation link.", error_code="INVALID_TOKEN")

    if not invitation.is_valid:
        return StaffActionResult(
            success=False,
            error="This invitation has expired or already been used.",
            error_code="INVITATION_EXPIRED",
        )

    if invitation.email != user.email:
        return StaffActionResult(
            success=False,
            error="This invitation was sent to a different email address.",
            error_code="EMAIL_MISMATCH",
        )

    try:
        invitation.accept(user)
    except ValueError as exc:
        return StaffActionResult(success=False, error=str(exc), error_code="ACCEPT_FAILED")

    return StaffActionResult(success=True)


def update_staff_role(staff_id: str, new_role_id: str, updated_by_staff) -> StaffActionResult:
    """Change a staff member's role."""
    from accounts.models import StoreStaff, Role

    try:
        staff = StoreStaff.objects.select_related("role").get(id=staff_id)
    except StoreStaff.DoesNotExist:
        return StaffActionResult(success=False, error="Staff member not found.")

    # Cannot change the owner's role
    if staff.is_owner:
        return StaffActionResult(success=False, error="Cannot change the owner's role.")

    # Cannot elevate to owner unless you're an owner
    try:
        new_role = Role.objects.get(id=new_role_id)
    except Role.DoesNotExist:
        return StaffActionResult(success=False, error="Role not found.")

    if new_role.is_owner_role and not updated_by_staff.is_owner:
        return StaffActionResult(success=False, error="Only owners can assign the Owner role.")

    old_role_name  = staff.role.name
    staff.role     = new_role
    staff.save(update_fields=["role", "updated_at"])

    _log_staff_action(
        staff=updated_by_staff,
        category="STAFF",
        action="staff.role_changed",
        description=f"Changed {staff.email}'s role from {old_role_name} to {new_role.name}",
        target_type="staff",
        target_id=str(staff.id),
        target_label=staff.email,
    )

    return StaffActionResult(success=True)


def remove_staff_member(staff_id: str, removed_by_staff) -> StaffActionResult:
    """Remove a staff member from the store."""
    from accounts.models import StoreStaff

    try:
        staff = StoreStaff.objects.get(id=staff_id)
    except StoreStaff.DoesNotExist:
        return StaffActionResult(success=False, error="Staff member not found.")

    if staff.is_owner:
        return StaffActionResult(success=False, error="Cannot remove the store owner.")

    if str(staff.user_id) == str(removed_by_staff.user_id):
        return StaffActionResult(success=False, error="You cannot remove yourself.")

    staff.status = StoreStaff.StaffStatus.INACTIVE
    staff.save(update_fields=["status", "updated_at"])

    _log_staff_action(
        staff=removed_by_staff,
        category="STAFF",
        action="staff.removed",
        description=f"Removed {staff.email} from store staff",
        target_type="staff",
        target_id=str(staff.id),
        target_label=staff.email,
    )

    return StaffActionResult(success=True)


def get_staff_list():
    """Return all active staff members with roles pre-fetched."""
    from accounts.models import StoreStaff
    return StoreStaff.objects.select_related("role").filter(
        status=StoreStaff.StaffStatus.ACTIVE
    ).order_by("role__sort_order", "full_name")


def get_pending_invitations():
    """Return all pending staff invitations."""
    from accounts.models import StaffInvitation
    return StaffInvitation.objects.select_related("role").filter(
        status=StaffInvitation.InvitationStatus.PENDING,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at")


def get_staff_activity(staff_id: str, limit: int = 50):
    from accounts.models import StaffActivityLog
    return StaffActivityLog.objects.filter(
        staff_id=staff_id
    ).order_by("-created_at")[:limit]


# ─────────────────────────────────────────────────────────────
# ROLE MANAGEMENT
# ─────────────────────────────────────────────────────────────

def get_roles():
    """Return all roles with permission counts."""
    from accounts.models import Role
    return Role.objects.prefetch_related("role_permissions__permission").order_by(
        "sort_order", "name"
    )


def create_role(
    name: str,
    description: str = "",
    permission_codenames: list = None,
    created_by_staff=None,
) -> tuple:
    """Create a custom role with the given permissions. Returns (Role, error_str)."""
    from accounts.models import Role, Permission, RolePermission
    from django.utils.text import slugify

    slug = slugify(name)
    if Role.objects.filter(slug=slug).exists():
        return None, f"A role named '{name}' already exists."

    role = Role.objects.create(
        name=name,
        slug=slug,
        description=description,
        is_system=False,
    )

    if permission_codenames:
        perms = Permission.objects.filter(codename__in=permission_codenames)
        for perm in perms:
            RolePermission.objects.create(
                role=role,
                permission=perm,
                granted_by=created_by_staff.user_id if created_by_staff else None,
            )
        role._permission_count = perms.count()
        role.save(update_fields=["_permission_count"])

    return role, ""


def update_role_permissions(
    role_id: str,
    permission_codenames: list,
    updated_by_staff=None,
) -> StaffActionResult:
    """Replace a role's permissions with the given set."""
    from accounts.models import Role, Permission, RolePermission

    try:
        role = Role.objects.get(id=role_id)
    except Role.DoesNotExist:
        return StaffActionResult(success=False, error="Role not found.")

    if role.is_owner_role:
        return StaffActionResult(success=False, error="Owner role permissions cannot be modified.")

    role.role_permissions.all().delete()
    perms = Permission.objects.filter(codename__in=permission_codenames)
    for perm in perms:
        RolePermission.objects.create(
            role=role,
            permission=perm,
            granted_by=updated_by_staff.user_id if updated_by_staff else None,
        )
    role._permission_count = perms.count()
    role.save(update_fields=["_permission_count"])

    return StaffActionResult(success=True)


# ─────────────────────────────────────────────────────────────
# CUSTOMER MANAGEMENT
# ─────────────────────────────────────────────────────────────

def get_customers(
    search: str = "",
    status: str = "",
    group_id: str = "",
    tag: str = "",
    page: int = 1,
    page_size: int = 25,
    sort: str = "-created_at",
):
    """Paginated customer list with filters."""
    from accounts.models import Customer

    qs = Customer.objects.prefetch_related("groups").order_by(sort)

    if search:
        qs = qs.filter(
            Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(phone__icontains=search)
            | Q(company__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    if group_id:
        qs = qs.filter(groups__id=group_id)
    if tag:
        qs = qs.filter(tags__contains=[tag])

    total  = qs.count()
    offset = (page - 1) * page_size
    items  = qs[offset:offset + page_size]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "num_pages": max(1, (total + page_size - 1) // page_size),
        "has_next": offset + page_size < total,
        "has_prev": page > 1,
        "items": list(items),
    }


def get_customer(customer_id: str):
    from accounts.models import Customer
    try:
        return Customer.objects.prefetch_related(
            "addresses", "groups", "notes"
        ).get(id=customer_id)
    except Customer.DoesNotExist:
        return None


def get_customer_by_email(email: str):
    from accounts.models import Customer
    try:
        return Customer.objects.get(email=email.strip().lower())
    except Customer.DoesNotExist:
        return None


@transaction.atomic
def create_customer(
    email: str,
    first_name: str = "",
    last_name: str = "",
    phone: str = "",
    company: str = "",
    tags: list = None,
    group_ids: list = None,
    staff_note: str = "",
    created_by_staff=None,
) -> tuple:
    """Manually create a customer. Returns (Customer, error_str)."""
    from accounts.models import Customer, CustomerGroup

    email = email.strip().lower()
    if Customer.objects.filter(email=email).exists():
        return None, f"A customer with email {email} already exists."

    customer = Customer.objects.create(
        email=email,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone.strip(),
        company=company.strip(),
        tags=tags or [],
        staff_note=staff_note.strip(),
        acquisition_source=Customer.AcquisitionSource.MANUAL,
    )

    if group_ids:
        groups = CustomerGroup.objects.filter(id__in=group_ids)
        customer.groups.set(groups)

    # Add to "All Customers" group
    all_group = CustomerGroup.objects.filter(is_system=True).first()
    if all_group:
        customer.groups.add(all_group)

    return customer, ""


def update_customer(
    customer_id: str,
    data: dict,
    updated_by_staff=None,
) -> tuple:
    """Update customer details. Returns (Customer, error_str)."""
    from accounts.models import Customer

    try:
        customer = Customer.objects.get(id=customer_id)
    except Customer.DoesNotExist:
        return None, "Customer not found."

    allowed_fields = {
        "first_name", "last_name", "phone", "company",
        "tags", "staff_note", "locale", "currency_code",
        "is_b2b", "tax_id", "tax_exempt_status",
        "email_marketing_consent", "sms_marketing_consent",
    }

    update_fields = []
    for field_name, value in data.items():
        if field_name in allowed_fields:
            setattr(customer, field_name, value)
            update_fields.append(field_name)

    if update_fields:
        update_fields.append("updated_at")
        customer.save(update_fields=update_fields)

    if "group_ids" in data:
        from accounts.models import CustomerGroup
        groups = CustomerGroup.objects.filter(id__in=data["group_ids"])
        # Always keep system groups
        system_groups = customer.groups.filter(is_system=True)
        customer.groups.set(list(groups) + list(system_groups))

    return customer, ""


def block_customer(customer_id: str, blocked_by_staff) -> StaffActionResult:
    from accounts.models import Customer
    updated = Customer.objects.filter(id=customer_id).update(
        status=Customer.CustomerStatus.BLOCKED,
        updated_at=timezone.now(),
    )
    if not updated:
        return StaffActionResult(success=False, error="Customer not found.")
    _log_staff_action(
        staff=blocked_by_staff, category="CUSTOMER",
        action="customer.blocked",
        description=f"Customer {customer_id} blocked",
        target_type="customer", target_id=customer_id,
    )
    return StaffActionResult(success=True)


def add_customer_note(
    customer_id: str,
    content: str,
    note_type: str = "GENERAL",
    is_pinned: bool = False,
    written_by_staff=None,
):
    """Add a note to a customer record."""
    from accounts.models import CustomerNote

    return CustomerNote.objects.create(
        customer_id=customer_id,
        written_by=written_by_staff.user_id if written_by_staff else uuid.uuid4(),
        written_by_name=written_by_staff.full_name if written_by_staff else "Staff",
        note_type=note_type,
        content=content.strip(),
        is_pinned=is_pinned,
    )


def get_customer_groups():
    """Return all customer groups with member counts."""
    from accounts.models import CustomerGroup
    return CustomerGroup.objects.order_by("sort_order", "name")


def get_customer_stats(period_days: int = 30) -> dict:
    """Dashboard-level customer stats."""
    from accounts.models import Customer
    from datetime import timedelta

    now   = timezone.now()
    start = now - timedelta(days=period_days)
    prev  = start - timedelta(days=period_days)

    curr = Customer.objects.filter(created_at__gte=start)
    prev_qs = Customer.objects.filter(created_at__range=(prev, start))

    total    = Customer.objects.filter(status=Customer.CustomerStatus.ACTIVE).count()
    new_curr = curr.count()
    new_prev = prev_qs.count()

    change_pct = 0.0
    if new_prev:
        change_pct = round((new_curr - new_prev) / new_prev * 100, 1)

    top_spenders = Customer.objects.filter(
        total_orders__gt=0
    ).order_by("-total_spent")[:5].values(
        "id", "email", "first_name", "last_name", "total_spent", "total_orders"
    )

    return {
        "total_customers":    total,
        "new_this_period":    new_curr,
        "new_prev_period":    new_prev,
        "new_change_pct":     change_pct,
        "avg_lifetime_value": Customer.objects.aggregate(
            avg=Avg("total_spent")
        )["avg"] or Decimal("0.00"),
        "total_with_orders": Customer.objects.filter(total_orders__gt=0).count(),
        "top_spenders":      list(top_spenders),
    }


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _log_staff_action(
    staff,
    category: str,
    action: str,
    description: str = "",
    target_type: str = "",
    target_id: str = "",
    target_label: str = "",
    before_state: dict = None,
    after_state: dict = None,
    request=None,
) -> None:
    from accounts.models import StaffActivityLog
    try:
        StaffActivityLog.objects.create(
            staff_id=staff.id,
            user_id=staff.user_id,
            staff_email=staff.email,
            staff_name=staff.full_name,
            category=category,
            action=action,
            description=description,
            target_type=target_type,
            target_id=str(target_id),
            target_label=target_label,
            before_state=before_state,
            after_state=after_state,
            ip_address=request.META.get("REMOTE_ADDR") if request else None,
        )
    except Exception as exc:
        logger.warning("Could not write staff activity log: %s", exc)


def _send_staff_invitation_email(invitation) -> None:
    logger.info(
        "Staff invitation email queued for %s (token=%s...)",
        invitation.email, invitation.token[:8],
    )
    # Wire to notifications app when built
