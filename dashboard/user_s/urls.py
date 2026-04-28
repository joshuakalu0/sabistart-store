"""
dashboard/user_s/urls.py
=========================
URL configuration for the user_s dashboard app.
Namespace: user_settings
"""
from django.urls import path
from . import views

app_name = "user_settings"

urlpatterns = [

    # ── TenantUser ────────────────────────────────────────────
    path("users/",                                    views.user_list,                 name="user_list"),
    path("users/create/",                             views.user_create,               name="user_create"),
    path("users/<uuid:pk>/",                          views.user_detail,               name="user_detail"),
    path("users/<uuid:pk>/edit/",                     views.user_edit,                 name="user_edit"),
    path("users/<uuid:pk>/unlock/",                   views.user_unlock,               name="user_unlock"),
    path("users/<uuid:pk>/force-password-reset/",     views.user_force_password_reset, name="user_force_password_reset"),
    path("users/<uuid:pk>/toggle-status/",            views.user_toggle_status,        name="user_toggle_status"),
    path("users/<uuid:pk>/soft-delete/",              views.user_soft_delete,          name="user_soft_delete"),

    # ── StoreStaff ────────────────────────────────────────────
    path("staff/",                                    views.staff_list,                name="staff_list"),
    path("staff/create/",                             views.staff_create,              name="staff_create"),
    path("staff/<int:pk>/",                           views.staff_detail,              name="staff_detail"),
    path("staff/<int:pk>/edit/",                      views.staff_edit,                name="staff_edit"),
    path("staff/<int:pk>/remove/",                    views.staff_remove,              name="staff_remove"),

    # ── Roles ─────────────────────────────────────────────────
    path("roles/",                                    views.role_list,                 name="role_list"),
    path("roles/create/",                             views.role_create,               name="role_create"),
    path("roles/<uuid:pk>/edit/",                     views.role_edit,                 name="role_edit"),
    path("roles/<uuid:pk>/delete/",                   views.role_delete,               name="role_delete"),

    # ── Permissions ───────────────────────────────────────────
    path("permissions/",                              views.permission_list,            name="permission_list"),

    # ── Customers ─────────────────────────────────────────────
    path("customers/",                                views.customer_list,             name="customer_list"),
    path("customers/<uuid:pk>/",                      views.customer_detail,           name="customer_detail"),
    path("customers/<uuid:pk>/edit/",                 views.customer_edit,             name="customer_edit"),
    path("customers/<uuid:pk>/add-note/",             views.customer_add_note,         name="customer_add_note"),
    path("customers/<uuid:pk>/toggle-status/",        views.customer_toggle_status,    name="customer_toggle_status"),
    path("customers/session/<uuid:pk>/terminate/",    views.customer_session_terminate,name="customer_session_terminate"),

    # ── Customer Groups ───────────────────────────────────────
    path("groups/",                                   views.group_list,                name="group_list"),
    path("groups/create/",                            views.group_create,              name="group_create"),
    path("groups/<uuid:pk>/edit/",                    views.group_edit,                name="group_edit"),
    path("groups/<uuid:pk>/delete/",                  views.group_delete,              name="group_delete"),

    # ── Audit Logs (read-only) ────────────────────────────────
    path("audit/logins/",                             views.login_audit_list,          name="login_audit_list"),
    path("audit/staff-activity/",                     views.staff_activity_list,       name="staff_activity_list"),
]
