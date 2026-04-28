"""
dashboard/user_s/views.py
==========================
Full dashboard views for the userauth app:
  - TenantUser management (list, detail, create, edit, actions)
  - StoreStaff management (list, create, edit)
  - Role & Permission management (list, create, edit, permission matrix)
  - Customer management (list, detail, edit, notes)
  - CustomerGroup management (list, create, edit)
  - Audit Logs (TenantLoginAuditLog, StaffActivityLog — read-only)
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import FeatureEntitlementEngine, enforce_quota
from dashboard.sidebar_utiles import main_sidebar
from public.userauth.models import (
    TenantUser,
    TenantLoginAuditLog,
    StoreStaff,
    Role,
    Permission,
    RolePermission,
    Customer,
    CustomerGroup,
    CustomerNote,
    CustomerAddress,
    CustomerSession,
    StaffActivityLog,
)
from .forms import (
    TenantUserForm,
    TenantUserEditForm,
    StoreStaffForm,
    RoleForm,
    CustomerForm,
    CustomerGroupForm,
    CustomerNoteForm,
    CustomerAddressForm,
)

logger = logging.getLogger("dashboard.user_s")


# ─────────────────────────────────────────────────────────────
# TENANT USER VIEWS
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def user_list(request, prefix):
    """Paginated, searchable list of all TenantUsers."""
    qs = TenantUser.objects.all()

    q = request.GET.get("q", "").strip()
    user_type = request.GET.get("user_type", "")
    status = request.GET.get("status", "")

    if q:
        qs = qs.filter(
            Q(email__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(phone__icontains=q)
        )
    if user_type:
        qs = qs.filter(user_type=user_type)
    if status:
        qs = qs.filter(account_status=status)

    paginator = Paginator(qs.order_by("-created_at"), 25)
    users = paginator.get_page(request.GET.get("page", 1))

    return render(request, "dashboard/user_s/user/list.html", {
        "page_title": "Users",
        "users": users,
        "q": q,
        "user_type": user_type,
        "status": status,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
        "user_type_choices": TenantUser.UserType.choices,
        "status_choices": TenantUser.AccountStatus.choices,
    })


@login_required
@dashboard_prefix_required
def user_create(request, prefix):
    """Create a new TenantUser (staff or customer)."""
    if request.method == "POST":
        form = TenantUserForm(request.POST)
        if form.is_valid():
            try:
                user = form.save(commit=False)
                raw_password = form.cleaned_data.get("password")
                if raw_password:
                    user.set_password(raw_password)
                user.save()
                messages.success(request, f"User '{user.email}' created successfully.")
                return redirect(reverse("dashboard:user_settings:user_detail", args=[prefix, user.pk]))
            except Exception as exc:
                logger.exception("Failed to create user: %s", exc)
                messages.error(request, f"Error creating user: {exc}")
    else:
        form = TenantUserForm()

    return render(request, "dashboard/user_s/user/form.html", {
        "page_title": "New User",
        "form": form,
        "is_edit": False,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def user_detail(request, prefix, pk):
    """Full user detail page: profile, security, sessions, login history."""
    user = get_object_or_404(TenantUser, pk=pk)
    login_logs = TenantLoginAuditLog.objects.filter(user=user).order_by("-created_at")[:20]
    sessions = CustomerSession.objects.none()
    if hasattr(user, "customer_profile") and user.customer_profile:
        sessions = user.customer_profile.sessions.filter(is_active=True).order_by("-last_active_at")[:10]

    return render(request, "dashboard/user_s/user/detail.html", {
        "page_title": f"User — {user.get_full_name()}",
        "user_obj": user,
        "login_logs": login_logs,
        "sessions": sessions,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def user_edit(request, prefix, pk):
    """Edit an existing TenantUser's profile and account settings."""
    user = get_object_or_404(TenantUser, pk=pk)

    if request.method == "POST":
        form = TenantUserEditForm(request.POST, instance=user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"User '{user.email}' updated.")
                return redirect(reverse("dashboard:user_settings:user_detail", args=[prefix, pk]))
            except Exception as exc:
                logger.exception("Failed to update user %s: %s", pk, exc)
                messages.error(request, f"Error updating user: {exc}")
    else:
        form = TenantUserEditForm(instance=user)

    return render(request, "dashboard/user_s/user/form.html", {
        "page_title": f"Edit User — {user.get_full_name()}",
        "form": form,
        "is_edit": True,
        "user_obj": user,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def user_unlock(request, prefix, pk):
    """Unlock an account locked due to failed login attempts."""
    user = get_object_or_404(TenantUser, pk=pk)
    user.unlock()
    messages.success(request, f"Account for '{user.email}' has been unlocked.")
    return redirect(reverse("dashboard:user_settings:user_detail", args=[prefix, pk]))


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def user_force_password_reset(request, prefix, pk):
    """Force the user to change their password on next login."""
    user = get_object_or_404(TenantUser, pk=pk)
    user.force_password_reset = True
    user.save(update_fields=["force_password_reset"])
    messages.success(request, f"'{user.email}' must reset their password on next login.")
    return redirect(reverse("dashboard:user_settings:user_detail", args=[prefix, pk]))


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def user_soft_delete(request, prefix, pk):
    """GDPR-compliant soft delete — irreversible. Requires POST confirmation."""
    user = get_object_or_404(TenantUser, pk=pk)
    try:
        user.soft_delete()
        messages.success(request, "User anonymised and permanently deleted.")
        return redirect(reverse("dashboard:user_settings:user_list", args=[prefix]))
    except Exception as exc:
        logger.exception("Failed to soft delete user %s: %s", pk, exc)
        messages.error(request, f"Error: {exc}")
        return redirect(reverse("dashboard:user_settings:user_detail", args=[prefix, pk]))


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def user_toggle_status(request, prefix, pk):
    """Toggle TenantUser account_status between ACTIVE and INACTIVE."""
    user = get_object_or_404(TenantUser, pk=pk)
    if user.account_status == TenantUser.AccountStatus.ACTIVE:
        user.account_status = TenantUser.AccountStatus.INACTIVE
        user.is_active = False
        msg = f"'{user.email}' deactivated."
    else:
        user.account_status = TenantUser.AccountStatus.ACTIVE
        user.is_active = True
        msg = f"'{user.email}' reactivated."
    user.save(update_fields=["account_status", "is_active"])
    messages.success(request, msg)
    return redirect(reverse("dashboard:user_settings:user_detail", args=[prefix, pk]))


# ─────────────────────────────────────────────────────────────
# STORE STAFF VIEWS
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def staff_list(request, prefix):
    """List all StoreStaff records with search and status filter."""
    qs = StoreStaff.objects.select_related("user", "role").all()

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    role_id = request.GET.get("role", "")

    if q:
        qs = qs.filter(Q(user__email__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if role_id:
        qs = qs.filter(role_id=role_id)

    paginator = Paginator(qs.order_by("role__sort_order", "user__first_name"), 25)
    staff = paginator.get_page(request.GET.get("page", 1))
    roles = Role.objects.filter(is_active=True).order_by("sort_order")

    return render(request, "dashboard/user_s/staff/list.html", {
        "page_title": "Store Staff",
        "staff": staff,
        "q": q,
        "status": status,
        "role_id": role_id,
        "roles": roles,
        "status_choices": StoreStaff.StaffStatus.choices,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def staff_create(request, prefix):
    """
    Create a StoreStaff record.
    The admin selects (or creates) a TenantUser, assigns a Role.
    The user can then be given their email + password to log in.
    """
    if request.method == "POST":
        form = StoreStaffForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    enforce_quota("staff_management")
                    staff = form.save()
                    FeatureEntitlementEngine().rebuild_quota("staff_management")
                    messages.success(request, f"Staff member '{staff.user.email}' added with role '{staff.role.name}'.")
                    return redirect(reverse("dashboard:user_settings:staff_detail", args=[prefix, staff.pk]))
            except Exception as exc:
                logger.exception("Failed to create staff: %s", exc)
                messages.error(request, f"Error: {exc}")
    else:
        form = StoreStaffForm()

    return render(request, "dashboard/user_s/staff/form.html", {
        "page_title": "Add Staff Member",
        "form": form,
        "is_edit": False,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def staff_detail(request, prefix, pk):
    """Staff member detail: overview, permissions, activity log."""
    staff = get_object_or_404(StoreStaff.objects.select_related("user", "role"), pk=pk)
    activity_logs = StaffActivityLog.objects.filter(staff=staff).order_by("-created_at")[:30]
    effective_perms = staff.get_effective_permissions()
    all_perms_by_category = {}
    for perm in Permission.objects.filter(is_active=True).order_by("category", "name"):
        cat = perm.get_category_display()
        all_perms_by_category.setdefault(cat, []).append({
            "perm": perm,
            "granted": perm.codename in effective_perms,
        })

    return render(request, "dashboard/user_s/staff/detail.html", {
        "page_title": f"Staff — {staff.user.get_full_name()}",
        "staff": staff,
        "activity_logs": activity_logs,
        "perms_by_category": all_perms_by_category,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def staff_edit(request, prefix, pk):
    """Edit a StoreStaff record: role, status, 2FA requirement."""
    staff = get_object_or_404(StoreStaff.objects.select_related("user", "role"), pk=pk)

    if request.method == "POST":
        form = StoreStaffForm(request.POST, instance=staff)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Staff record for '{staff.user.email}' updated.")
                return redirect(reverse("dashboard:user_settings:staff_detail", args=[prefix, pk]))
            except Exception as exc:
                logger.exception("Failed to edit staff %s: %s", pk, exc)
                messages.error(request, f"Error: {exc}")
    else:
        form = StoreStaffForm(instance=staff)

    return render(request, "dashboard/user_s/staff/form.html", {
        "page_title": f"Edit Staff — {staff.user.get_full_name()}",
        "form": form,
        "is_edit": True,
        "staff": staff,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def staff_remove(request, prefix, pk):
    """Set a staff member's status to INACTIVE (soft remove)."""
    staff = get_object_or_404(StoreStaff, pk=pk)
    if staff.is_owner:
        messages.error(request, "Cannot remove the store owner.")
        return redirect(reverse("dashboard:user_settings:staff_detail", args=[prefix, pk]))
    staff.status = StoreStaff.StaffStatus.INACTIVE
    staff.save(update_fields=["status"])
    FeatureEntitlementEngine().rebuild_quota("staff_management")
    messages.success(request, f"'{staff.user.email}' removed from active staff.")
    return redirect(reverse("dashboard:user_settings:staff_list", args=[prefix]))


# ─────────────────────────────────────────────────────────────
# ROLE & PERMISSION VIEWS
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def role_list(request, prefix):
    """List all roles with permission counts."""
    qs = Role.objects.annotate(perm_count=Count("role_permissions")).order_by("sort_order", "name")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

    paginator = Paginator(qs, 25)
    roles = paginator.get_page(request.GET.get("page", 1))

    return render(request, "dashboard/user_s/role/list.html", {
        "page_title": "Roles",
        "roles": roles,
        "q": q,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def role_create(request, prefix):
    """Create a new custom Role with permission assignment."""
    all_permissions = Permission.objects.filter(is_active=True).order_by("category", "name")
    perms_by_category = {}
    for p in all_permissions:
        perms_by_category.setdefault(p.get_category_display(), []).append(p)

    if request.method == "POST":
        form = RoleForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    role = form.save()
                    # Handle permission selection from POST
                    selected_codenames = request.POST.getlist("permissions")
                    perms = Permission.objects.filter(codename__in=selected_codenames, is_active=True)
                    for perm in perms:
                        RolePermission.objects.create(role=role, permission=perm)
                    messages.success(request, f"Role '{role.name}' created with {perms.count()} permissions.")
                    return redirect(reverse("dashboard:user_settings:role_list", args=[prefix]))
            except Exception as exc:
                logger.exception("Failed to create role: %s", exc)
                messages.error(request, f"Error: {exc}")
    else:
        form = RoleForm()

    return render(request, "dashboard/user_s/role/form.html", {
        "page_title": "New Role",
        "form": form,
        "is_edit": False,
        "perms_by_category": perms_by_category,
        "selected_perms": [],
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def role_edit(request, prefix, pk):
    """Edit a Role's details and update its permission set."""
    role = get_object_or_404(Role, pk=pk)

    if role.is_system and role.system_slug == Role.SystemRole.OWNER:
        messages.error(request, "The Owner role cannot be modified.")
        return redirect(reverse("dashboard:user_settings:role_list", args=[prefix]))

    all_permissions = Permission.objects.filter(is_active=True).order_by("category", "name")
    perms_by_category = {}
    for p in all_permissions:
        perms_by_category.setdefault(p.get_category_display(), []).append(p)
    current_perms = set(role.get_permissions())

    if request.method == "POST":
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    selected_codenames = request.POST.getlist("permissions")
                    role.role_permissions.all().delete()
                    perms = Permission.objects.filter(codename__in=selected_codenames, is_active=True)
                    for perm in perms:
                        RolePermission.objects.create(role=role, permission=perm)
                    messages.success(request, f"Role '{role.name}' updated.")
                    return redirect(reverse("dashboard:user_settings:role_list", args=[prefix]))
            except Exception as exc:
                logger.exception("Failed to edit role %s: %s", pk, exc)
                messages.error(request, f"Error: {exc}")
    else:
        form = RoleForm(instance=role)

    return render(request, "dashboard/user_s/role/form.html", {
        "page_title": f"Edit Role — {role.name}",
        "form": form,
        "is_edit": True,
        "role": role,
        "perms_by_category": perms_by_category,
        "selected_perms": current_perms,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def role_delete(request, prefix, pk):
    """Soft-delete (deactivate) a custom Role. System roles cannot be deleted."""
    role = get_object_or_404(Role, pk=pk)
    if role.is_system:
        messages.error(request, f"System role '{role.name}' cannot be deleted.")
        return redirect(reverse("dashboard:user_settings:role_list", args=[prefix]))
    try:
        role.delete()
        messages.success(request, f"Role '{role.name}' deleted.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect(reverse("dashboard:user_settings:role_list", args=[prefix]))


@login_required
@dashboard_prefix_required
def permission_list(request, prefix):
    """Read-only view of all system permissions grouped by category."""
    q = request.GET.get("q", "").strip()
    cat = request.GET.get("category", "")
    qs = Permission.objects.filter(is_active=True).order_by("category", "name")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(codename__icontains=q))
    if cat:
        qs = qs.filter(category=cat)

    perms_by_category = {}
    for p in qs:
        perms_by_category.setdefault(p.get_category_display(), []).append(p)

    return render(request, "dashboard/user_s/permission/list.html", {
        "page_title": "Permissions",
        "perms_by_category": perms_by_category,
        "q": q,
        "cat": cat,
        "categories": Permission.PERMISSION_CATEGORIES,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


# ─────────────────────────────────────────────────────────────
# CUSTOMER VIEWS
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def customer_list(request, prefix):
    """Paginated customer list with search, status, group, and tier filters."""
    qs = Customer.objects.select_related("user").prefetch_related("groups")

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    group_id = request.GET.get("group", "")
    tier = request.GET.get("tier", "")

    if q:
        qs = qs.filter(
            Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(company__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if group_id:
        qs = qs.filter(groups__id=group_id)
    if tier:
        qs = qs.filter(tier=tier)

    paginator = Paginator(qs.order_by("-created_at"), 25)
    customers = paginator.get_page(request.GET.get("page", 1))
    groups = CustomerGroup.objects.order_by("sort_order")

    return render(request, "dashboard/user_s/customer/list.html", {
        "page_title": "Customers",
        "customers": customers,
        "q": q,
        "status": status,
        "group_id": group_id,
        "tier": tier,
        "groups": groups,
        "status_choices": Customer.Status.choices,
        "tier_choices": Customer.CustomerTier.choices,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def customer_detail(request, prefix, pk):
    """Customer detail: profile, stats, addresses, notes, sessions."""
    customer = get_object_or_404(
        Customer.objects.select_related("user").prefetch_related("addresses", "notes__written_by", "groups", "sessions"),
        pk=pk
    )
    # Inline note form
    note_form = CustomerNoteForm()
    return render(request, "dashboard/user_s/customer/detail.html", {
        "page_title": f"Customer — {customer.display_name}",
        "customer": customer,
        "note_form": note_form,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def customer_edit(request, prefix, pk):
    """Edit a Customer's commerce profile (not identity — that's TenantUser)."""
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Customer updated.")
                return redirect(reverse("dashboard:user_settings:customer_detail", args=[prefix, pk]))
            except Exception as exc:
                logger.exception("Failed to update customer %s: %s", pk, exc)
                messages.error(request, f"Error: {exc}")
    else:
        form = CustomerForm(instance=customer)

    return render(request, "dashboard/user_s/customer/form.html", {
        "page_title": f"Edit Customer — {customer.display_name}",
        "form": form,
        "customer": customer,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def customer_add_note(request, prefix, pk):
    """Append-only: add a note to a customer record."""
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerNoteForm(request.POST)
    if form.is_valid():
        try:
            note = form.save(commit=False)
            note.customer = customer
            note.written_by = request.user.pk  # UUID of acting staff
            note.written_by_name = request.user.get_full_name() or request.user.username
            note.save()
            messages.success(request, "Note added.")
        except Exception as exc:
            messages.error(request, f"Error adding note: {exc}")
    else:
        messages.error(request, "Invalid note submission.")
    return redirect(reverse("dashboard:user_settings:customer_detail", args=[prefix, pk]))


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def customer_toggle_status(request, prefix, pk):
    """Toggle a customer's status between ACTIVE and BLOCKED."""
    customer = get_object_or_404(Customer, pk=pk)
    if customer.status == Customer.Status.ACTIVE:
        customer.status = Customer.Status.BLOCKED
        msg = f"Customer '{customer.display_name}' blocked."
    else:
        customer.status = Customer.Status.ACTIVE
        msg = f"Customer '{customer.display_name}' unblocked."
    customer.save(update_fields=["status"])
    messages.success(request, msg)
    return redirect(reverse("dashboard:user_settings:customer_detail", args=[prefix, pk]))


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def customer_session_terminate(request, prefix, pk):
    """Terminate a single customer session."""
    session = get_object_or_404(CustomerSession, pk=pk)
    customer_pk = session.customer_id
    session.terminate()
    messages.success(request, "Session terminated.")
    return redirect(reverse("dashboard:user_settings:customer_detail", args=[prefix, customer_pk]))


# ─────────────────────────────────────────────────────────────
# CUSTOMER GROUP VIEWS
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def group_list(request, prefix):
    """List all CustomerGroups."""
    qs = CustomerGroup.objects.annotate(count=Count("customers")).order_by("sort_order", "name")
    paginator = Paginator(qs, 25)
    groups = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/user_s/group/list.html", {
        "page_title": "Customer Groups",
        "groups": groups,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def group_create(request, prefix):
    """Create a Customer Group."""
    if request.method == "POST":
        form = CustomerGroupForm(request.POST)
        if form.is_valid():
            try:
                group = form.save()
                messages.success(request, f"Group '{group.name}' created.")
                return redirect(reverse("dashboard:user_settings:group_list", args=[prefix]))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
    else:
        form = CustomerGroupForm()

    return render(request, "dashboard/user_s/group/form.html", {
        "page_title": "New Customer Group",
        "form": form,
        "is_edit": False,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def group_edit(request, prefix, pk):
    """Edit a Customer Group."""
    group = get_object_or_404(CustomerGroup, pk=pk)
    if group.is_system:
        messages.error(request, "System groups cannot be edited.")
        return redirect(reverse("dashboard:user_settings:group_list", args=[prefix]))

    if request.method == "POST":
        form = CustomerGroupForm(request.POST, instance=group)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Group '{group.name}' updated.")
                return redirect(reverse("dashboard:user_settings:group_list", args=[prefix]))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
    else:
        form = CustomerGroupForm(instance=group)

    return render(request, "dashboard/user_s/group/form.html", {
        "page_title": f"Edit Group — {group.name}",
        "form": form,
        "is_edit": True,
        "group": group,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def group_delete(request, prefix, pk):
    """Delete a customer group. System groups are protected."""
    group = get_object_or_404(CustomerGroup, pk=pk)
    try:
        name = group.name
        group.delete()
        messages.success(request, f"Group '{name}' deleted.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect(reverse("dashboard:user_settings:group_list", args=[prefix]))


# ─────────────────────────────────────────────────────────────
# AUDIT LOG VIEWS (READ-ONLY)
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def login_audit_list(request, prefix):
    """Read-only list of all tenant login attempts."""
    qs = TenantLoginAuditLog.objects.all()

    result = request.GET.get("result", "")
    suspicious = request.GET.get("suspicious", "")
    q = request.GET.get("q", "").strip()

    if q:
        qs = qs.filter(Q(attempted_email__icontains=q) | Q(ip_address__icontains=q))
    if result:
        qs = qs.filter(result=result)
    if suspicious == "1":
        qs = qs.filter(is_suspicious=True)

    paginator = Paginator(qs.order_by("-created_at"), 50)
    logs = paginator.get_page(request.GET.get("page", 1))

    return render(request, "dashboard/user_s/audit/login_list.html", {
        "page_title": "Login Audit Log",
        "logs": logs,
        "q": q,
        "result": result,
        "suspicious": suspicious,
        "result_choices": TenantLoginAuditLog.LoginResult.choices,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })


@login_required
@dashboard_prefix_required
def staff_activity_list(request, prefix):
    """Read-only list of all staff activity log entries."""
    qs = StaffActivityLog.objects.select_related("staff", "user").all()

    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")

    if q:
        qs = qs.filter(Q(staff_email__icontains=q) | Q(action__icontains=q) | Q(target_label__icontains=q))
    if category:
        qs = qs.filter(category=category)

    paginator = Paginator(qs.order_by("-created_at"), 50)
    logs = paginator.get_page(request.GET.get("page", 1))

    return render(request, "dashboard/user_s/audit/staff_activity_list.html", {
        "page_title": "Staff Activity Log",
        "logs": logs,
        "q": q,
        "category": category,
        "category_choices": StaffActivityLog.ActionCategory.choices,
        "prefix": prefix,
        "sidebar": main_sidebar(prefix),
    })
