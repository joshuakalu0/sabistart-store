"""
userauth/decorators.py
======================
Permission and access control decorators for views.
"""

from functools import wraps
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse


def staff_required():
    """
    Decorator to ensure user is a staff member.
    
    Usage:
        @login_required
        @staff_required()
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                tenant_profile = request.user.tenant_profile
                if not tenant_profile.is_staff_member():
                    messages.error(request, 'Staff access required')
                    return HttpResponseForbidden('Staff access required')
            except Exception:
                messages.error(request, 'User profile not found')
                return HttpResponseForbidden('User profile not found')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def permission_required(permission_codename: str):
    """
    Decorator to check if user has a specific permission.
    
    Usage:
        @login_required
        @staff_required()
        @permission_required('customer.view')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                tenant_profile = request.user.tenant_profile
                if not tenant_profile.has_permission(permission_codename):
                    messages.error(
                        request,
                        f'You do not have permission to perform this action. Required: {permission_codename}'
                    )
                    return HttpResponseForbidden(
                        f'Permission denied. Required: {permission_codename}'
                    )
            except Exception:
                messages.error(request, 'User profile not found')
                return HttpResponseForbidden('User profile not found')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def role_required(role_slug: str):
    """
    Decorator to check if user has a specific role.
    
    Usage:
        @login_required
        @role_required('admin')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                tenant_profile = request.user.tenant_profile
                if not tenant_profile.roles.filter(slug=role_slug, is_active=True).exists():
                    messages.error(
                        request,
                        f'You do not have the required role: {role_slug}'
                    )
                    return HttpResponseForbidden(f'Role required: {role_slug}')
            except Exception:
                messages.error(request, 'User profile not found')
                return HttpResponseForbidden('User profile not found')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def customer_only():
    """
    Decorator to ensure user is a customer.
    
    Usage:
        @login_required
        @customer_only()
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                tenant_profile = request.user.tenant_profile
                if not tenant_profile.is_customer():
                    messages.error(request, 'Customer access only')
                    return HttpResponseForbidden('Customer access only')
            except Exception:
                messages.error(request, 'User profile not found')
                return HttpResponseForbidden('User profile not found')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def any_permission_required(*permission_codenames):
    """
    Decorator to check if user has ANY of the specified permissions.
    
    Usage:
        @login_required
        @any_permission_required('customer.view', 'customer.edit')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                tenant_profile = request.user.tenant_profile
                has_permission = any(
                    tenant_profile.has_permission(perm)
                    for perm in permission_codenames
                )
                
                if not has_permission:
                    messages.error(
                        request,
                        f'You do not have any of the required permissions: {", ".join(permission_codenames)}'
                    )
                    return HttpResponseForbidden('Permission denied')
            except Exception:
                messages.error(request, 'User profile not found')
                return HttpResponseForbidden('User profile not found')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
