# from django.contrib import admin
# from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
# from django.contrib.auth.models import User as AuthUser
# from django.utils.html import format_html
# from django.urls import reverse
# from django.utils.safestring import mark_safe
# from django.db.models import Count, Sum, Avg
# from django.utils.translation import gettext_lazy as _
# from django.contrib.admin import SimpleListFilter
# from django.utils import timezone
# from datetime import timedelta

# from .models import Permission, Role, User, UserAddress, UserSession


# class ActiveFilter(SimpleListFilter):
#     """Custom filter for active/inactive records."""
#     title = _('Status')
#     parameter_name = 'is_active'

#     def lookups(self, request, model_admin):
#         return (
#             ('1', _('Active')),
#             ('0', _('Inactive')),
#         )

#     def queryset(self, request, queryset):
#         if self.value() == '1':
#             return queryset.filter(is_active=True)
#         if self.value() == '0':
#             return queryset.filter(is_active=False)
#         return queryset


# class RecentActivityFilter(SimpleListFilter):
#     """Filter users by recent activity."""
#     title = _('Recent Activity')
#     parameter_name = 'recent_activity'

#     def lookups(self, request, model_admin):
#         return (
#             ('today', _('Today')),
#             ('week', _('This Week')),
#             ('month', _('This Month')),
#             ('inactive', _('Inactive 30+ Days')),
#         )

#     def queryset(self, request, queryset):
#         now = timezone.now()
#         if self.value() == 'today':
#             return queryset.filter(last_activity__gte=now - timedelta(days=1))
#         elif self.value() == 'week':
#             return queryset.filter(last_activity__gte=now - timedelta(days=7))
#         elif self.value() == 'month':
#             return queryset.filter(last_activity__gte=now - timedelta(days=30))
#         elif self.value() == 'inactive':
#             return queryset.filter(last_activity__lt=now - timedelta(days=30))
#         return queryset


# @admin.register(Permission)
# class PermissionAdmin(admin.ModelAdmin):
#     """
#     Admin interface for custom permissions.
#     Provides comprehensive permission management with categorization.
#     """

#     list_display = [
#         'name', 'codename', 'category_badge', 'is_system_badge',
#         'is_active_badge', 'roles_count', 'users_count', 'created_at'
#     ]
#     list_filter = ['category', 'is_system', ActiveFilter, 'created_at']
#     search_fields = ['name', 'codename', 'description']
#     list_editable = ['is_active']
#     readonly_fields = ['id', 'created_at', 'updated_at', 'roles_count', 'users_count']
#     fieldsets = (
#         (_('Basic Information'), {
#             'fields': ('name', 'codename', 'description', 'category')
#         }),
#         (_('Settings'), {
#             'fields': ('is_system', 'is_active')
#         }),
#         (_('Statistics'), {
#             'fields': ('roles_count', 'users_count'),
#             'classes': ('collapse',)
#         }),
#         (_('Metadata'), {
#             'fields': ('id', 'created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )

#     def get_queryset(self, request):
#         return super().get_queryset(request).annotate(
#             roles_count=Count('roles', distinct=True),
#             users_count=Count('users', distinct=True)
#         )

#     def category_badge(self, obj):
#         colors = {
#             'product': 'blue', 'order': 'green', 'customer': 'purple',
#             'inventory': 'orange', 'analytics': 'red', 'settings': 'gray',
#             'financial': 'yellow', 'marketing': 'pink'
#         }
#         color = colors.get(obj.category, 'gray')
#         return format_html(
#             '<span class="badge badge-{}">{}</span>',
#             color, obj.get_category_display()
#         )
#     category_badge.short_description = _('Category')

#     def is_system_badge(self, obj):
#         if obj.is_system:
#             return format_html('<span class="badge badge-warning">System</span>')
#         return format_html('<span class="badge badge-secondary">Custom</span>')
#     is_system_badge.short_description = _('Type')

#     def is_active_badge(self, obj):
#         if obj.is_active:
#             return format_html('<span class="badge badge-success">Active</span>')
#         return format_html('<span class="badge badge-danger">Inactive</span>')
#     is_active_badge.short_description = _('Status')

#     def roles_count(self, obj):
#         return obj.roles_count
#     roles_count.short_description = _('Roles')
#     roles_count.admin_order_field = 'roles_count'

#     def users_count(self, obj):
#         return obj.users_count
#     users_count.short_description = _('Users')
#     users_count.admin_order_field = 'users_count'

#     def has_delete_permission(self, request, obj=None):
#         if obj and obj.is_system:
#             return False
#         return super().has_delete_permission(request, obj)


# @admin.register(Role)
# class RoleAdmin(admin.ModelAdmin):
#     """
#     Admin interface for roles with hierarchical display and permission management.
#     """

#     list_display = [
#         'name', 'role_type_badge', 'level_badge', 'parent_role',
#         'permissions_count', 'users_count', 'is_active_badge', 'created_at'
#     ]
#     list_filter = ['role_type', 'level', 'is_system', ActiveFilter, 'created_at']
#     search_fields = ['name', 'slug', 'description']
#     list_editable = ['is_active']
#     filter_horizontal = ['permissions']
#     readonly_fields = ['id', 'created_at', 'updated_at', 'permissions_count', 'users_count']
#     prepopulated_fields = {'slug': ('name',)}

#     fieldsets = (
#         (_('Basic Information'), {
#             'fields': ('name', 'slug', 'description')
#         }),
#         (_('Role Configuration'), {
#             'fields': ('role_type', 'level', 'parent_role', 'max_users')
#         }),
#         (_('Permissions'), {
#             'fields': ('permissions',)
#         }),
#         (_('Settings'), {
#             'fields': ('is_system', 'is_active')
#         }),
#         (_('Statistics'), {
#             'fields': ('permissions_count', 'users_count'),
#             'classes': ('collapse',)
#         }),
#         (_('Metadata'), {
#             'fields': ('id', 'created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )

#     def get_queryset(self, request):
#         return super().get_queryset(request).select_related('parent_role').annotate(
#             permissions_count=Count('permissions', distinct=True),
#             users_count=Count('users', distinct=True)
#         )

#     def role_type_badge(self, obj):
#         colors = {'system': 'danger', 'business': 'warning', 'custom': 'info'}
#         color = colors.get(obj.role_type, 'secondary')
#         return format_html(
#             '<span class="badge badge-{}">{}</span>',
#             color, obj.get_role_type_display()
#         )
#     role_type_badge.short_description = _('Type')

#     def level_badge(self, obj):
#         colors = {1: 'danger', 2: 'warning', 3: 'info', 4: 'success', 5: 'secondary'}
#         color = colors.get(obj.level, 'secondary')
#         return format_html(
#             '<span class="badge badge-{}">Level {} - {}</span>',
#             color, obj.level, obj.get_level_display()
#         )
#     level_badge.short_description = _('Level')

#     def is_active_badge(self, obj):
#         if obj.is_active:
#             return format_html('<span class="badge badge-success">Active</span>')
#         return format_html('<span class="badge badge-danger">Inactive</span>')
#     is_active_badge.short_description = _('Status')

#     def permissions_count(self, obj):
#         return obj.permissions_count
#     permissions_count.short_description = _('Permissions')
#     permissions_count.admin_order_field = 'permissions_count'

#     def users_count(self, obj):
#         return obj.users_count
#     users_count.short_description = _('Users')
#     users_count.admin_order_field = 'users_count'

#     def has_delete_permission(self, request, obj=None):
#         if obj and obj.is_system:
#             return False
#         return super().has_delete_permission(request, obj)


# class UserAddressInline(admin.TabularInline):
#     """Inline admin for user addresses."""
#     model = UserAddress
#     extra = 0
#     fields = [
#         'label', 'address_type', 'full_name', 'phone',
#         'address_line1', 'city', 'country', 'is_default', 'is_active'
#     ]
#     readonly_fields = ['id']


# class UserSessionInline(admin.TabularInline):
#     """Inline admin for user sessions."""
#     model = UserSession
#     extra = 0
#     fields = ['ip_address', 'device_type', 'browser', 'last_activity', 'is_active']
#     readonly_fields = ['session_key', 'user_agent', 'last_activity']
#     max_num = 5

#     def get_queryset(self, request):
#         return super().get_queryset(request).order_by('-last_activity')[:5]


# @admin.register(User)
# class UserAdmin(admin.ModelAdmin):
#     """
#     Comprehensive admin interface for users with advanced filtering and management.
#     """

#     list_display = [
#         'get_full_name', 'email', 'user_type_badge', 'status_badge',
#         'verification_status', 'total_spent', 'total_orders',
#         'last_activity', 'created_at'
#     ]
#     list_filter = [
#         'user_type', 'status', 'email_verified', 'phone_verified',
#         'customer_tier', RecentActivityFilter, 'created_at'
#     ]
#     search_fields = [
#         'first_name', 'last_name', 'email', 'phone',
#         'employee_id', 'auth_user__username'
#     ]
#     list_editable = ['status']
#     filter_horizontal = ['roles', 'custom_permissions']
#     readonly_fields = [
#         'id', 'auth_user', 'total_orders', 'total_spent', 'average_order_value',
#         'loyalty_points', 'last_login_ip', 'failed_login_attempts',
#         'created_at', 'updated_at', 'last_activity'
#     ]
#     inlines = [UserAddressInline, UserSessionInline]

#     fieldsets = (
#         (_('Basic Information'), {
#             'fields': (
#                 'auth_user', 'user_type', 'status',
#                 ('first_name', 'last_name'), 'email', 'phone'
#             )
#         }),
#         (_('Personal Details'), {
#             'fields': ('date_of_birth', 'gender'),
#             'classes': ('collapse',)
#         }),
#         (_('Professional Information'), {
#             'fields': (
#                 'employee_id', 'department', 'job_title',
#                 'hire_date', 'salary'
#             ),
#             'classes': ('collapse',)
#         }),
#         (_('Roles & Permissions'), {
#             'fields': ('roles', 'custom_permissions')
#         }),
#         (_('Verification & Security'), {
#             'fields': (
#                 ('email_verified', 'phone_verified'),
#                 'two_factor_enabled', 'last_login_ip',
#                 'failed_login_attempts', 'account_locked_until'
#             ),
#             'classes': ('collapse',)
#         }),
#         (_('Customer Metrics'), {
#             'fields': (
#                 ('total_orders', 'total_spent'),
#                 'average_order_value', 'loyalty_points', 'customer_tier'
#             ),
#             'classes': ('collapse',)
#         }),
#         (_('Preferences'), {
#             'fields': (
#                 ('preferred_language', 'preferred_currency', 'timezone'),
#                 ('marketing_consent', 'newsletter_subscription')
#             ),
#             'classes': ('collapse',)
#         }),
#         (_('Metadata'), {
#             'fields': ('notes', 'tags', 'metadata'),
#             'classes': ('collapse',)
#         }),
#         (_('System Information'), {
#             'fields': ('id', 'created_at', 'updated_at', 'last_activity'),
#             'classes': ('collapse',)
#         }),
#     )

#     def get_queryset(self, request):
#         return super().get_queryset(request).select_related('auth_user')

#     def user_type_badge(self, obj):
#         colors = {
#             'staff': 'primary', 'customer': 'success',
#             'vendor': 'warning', 'affiliate': 'info'
#         }
#         color = colors.get(obj.user_type, 'secondary')
#         return format_html(
#             '<span class="badge badge-{}">{}</span>',
#             color, obj.get_user_type_display()
#         )
#     user_type_badge.short_description = _('Type')

#     def status_badge(self, obj):
#         colors = {
#             'active': 'success', 'inactive': 'secondary',
#             'suspended': 'warning', 'pending': 'info', 'banned': 'danger'
#         }
#         color = colors.get(obj.status, 'secondary')
#         return format_html(
#             '<span class="badge badge-{}">{}</span>',
#             color, obj.get_status_display()
#         )
#     status_badge.short_description = _('Status')

#     def verification_status(self, obj):
#         email_icon = '✓' if obj.email_verified else '✗'
#         phone_icon = '✓' if obj.phone_verified else '✗'
#         return format_html(
#             'Email: {} | Phone: {}',
#             email_icon, phone_icon
#         )
#     verification_status.short_description = _('Verified')

#     def get_full_name(self, obj):
#         name = obj.get_full_name()
#         if obj.user_type == 'staff' and obj.employee_id:
#             name += f" ({obj.employee_id})"
#         return name
#     get_full_name.short_description = _('Name')
#     get_full_name.admin_order_field = 'first_name'

#     # Custom actions
#     actions = [
#         'activate_users', 'deactivate_users', 'verify_email',
#         'send_welcome_email', 'reset_failed_attempts'
#     ]

#     def activate_users(self, request, queryset):
#         updated = queryset.update(status='active')
#         self.message_user(
#             request,
#             f'{updated} users were successfully activated.'
#         )
#     activate_users.short_description = _('Activate selected users')

#     def deactivate_users(self, request, queryset):
#         updated = queryset.update(status='inactive')
#         self.message_user(
#             request,
#             f'{updated} users were successfully deactivated.'
#         )
#     deactivate_users.short_description = _('Deactivate selected users')

#     def verify_email(self, request, queryset):
#         updated = queryset.update(email_verified=True)
#         self.message_user(
#             request,
#             f'{updated} users had their email verified.'
#         )
#     verify_email.short_description = _('Verify email for selected users')

#     def reset_failed_attempts(self, request, queryset):
#         updated = queryset.update(
#             failed_login_attempts=0,
#             account_locked_until=None
#         )
#         self.message_user(
#             request,
#             f'Reset failed login attempts for {updated} users.'
#         )
#     reset_failed_attempts.short_description = _('Reset failed login attempts')


# @admin.register(UserAddress)
# class UserAddressAdmin(admin.ModelAdmin):
#     """
#     Admin interface for user addresses with geographical filtering.
#     """

#     list_display = [
#         'user', 'label', 'address_type_badge', 'full_name',
#         'city', 'country', 'is_default_badge', 'is_active_badge'
#     ]
#     list_filter = ['address_type', 'country', 'is_default', ActiveFilter]
#     search_fields = [
#         'user__first_name', 'user__last_name', 'user__email',
#         'full_name', 'company', 'city', 'country'
#     ]
#     list_editable = ['is_active']
#     readonly_fields = ['id', 'created_at', 'updated_at']

#     fieldsets = (
#         (_('User & Type'), {
#             'fields': ('user', 'address_type', 'label')
#         }),
#         (_('Contact Information'), {
#             'fields': ('full_name', 'company', 'phone')
#         }),
#         (_('Address Details'), {
#             'fields': (
#                 'address_line1', 'address_line2',
#                 ('city', 'state_province'),
#                 ('postal_code', 'country')
#             )
#         }),
#         (_('Geolocation'), {
#             'fields': ('latitude', 'longitude'),
#             'classes': ('collapse',)
#         }),
#         (_('Settings'), {
#             'fields': ('is_default', 'is_active', 'delivery_instructions')
#         }),
#         (_('Metadata'), {
#             'fields': ('id', 'created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )

#     def address_type_badge(self, obj):
#         colors = {'billing': 'warning', 'shipping': 'info', 'both': 'success'}
#         color = colors.get(obj.address_type, 'secondary')
#         return format_html(
#             '<span class="badge badge-{}">{}</span>',
#             color, obj.get_address_type_display()
#         )
#     address_type_badge.short_description = _('Type')

#     def is_default_badge(self, obj):
#         if obj.is_default:
#             return format_html('<span class="badge badge-primary">Default</span>')
#         return ''
#     is_default_badge.short_description = _('Default')

#     def is_active_badge(self, obj):
#         if obj.is_active:
#             return format_html('<span class="badge badge-success">Active</span>')
#         return format_html('<span class="badge badge-danger">Inactive</span>')
#     is_active_badge.short_description = _('Status')


# @admin.register(UserSession)
# class UserSessionAdmin(admin.ModelAdmin):
#     """
#     Admin interface for user sessions with security monitoring.
#     """

#     list_display = [
#         'user', 'ip_address', 'device_type', 'browser',
#         'country', 'last_activity', 'is_active_badge', 'expires_at'
#     ]
#     list_filter = [
#         'device_type', 'browser', 'country', 'is_active',
#         'last_activity', 'expires_at'
#     ]
#     search_fields = [
#         'user__first_name', 'user__last_name', 'user__email',
#         'ip_address', 'session_key'
#     ]
#     readonly_fields = [
#         'id', 'session_key', 'user_agent', 'created_at', 'updated_at'
#     ]
#     date_hierarchy = 'last_activity'

#     fieldsets = (
#         (_('Session Information'), {
#             'fields': ('user', 'session_key', 'is_active', 'expires_at')
#         }),
#         (_('Device & Browser'), {
#             'fields': ('ip_address', 'device_type', 'browser', 'os', 'user_agent')
#         }),
#         (_('Location'), {
#             'fields': ('country', 'city')
#         }),
#         (_('Activity'), {
#             'fields': ('last_activity',)
#         }),
#         (_('Metadata'), {
#             'fields': ('id', 'created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )

#     def is_active_badge(self, obj):
#         if obj.is_active and not obj.is_expired():
#             return format_html('<span class="badge badge-success">Active</span>')
#         return format_html('<span class="badge badge-danger">Expired</span>')
#     is_active_badge.short_description = _('Status')

#     actions = ['terminate_sessions']

#     def terminate_sessions(self, request, queryset):
#         updated = queryset.update(is_active=False)
#         self.message_user(
#             request,
#             f'{updated} sessions were terminated.'
#         )
#     terminate_sessions.short_description = _('Terminate selected sessions')


# # Customize the admin site
# admin.site.site_header = _('User Management System')
# admin.site.site_title = _('User Admin')
# admin.site.index_title = _('Welcome to User Management')
