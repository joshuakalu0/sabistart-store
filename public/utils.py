from __future__ import annotations

import ipaddress
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from public.cart.utiles.cart import merge_guest_cart_into_user_cart
from public.storefront.services import (
    build_seo_context as storefront_build_seo_context,
    ensure_request_session,
    get_cart_summary,
    get_or_create_cart as storefront_get_or_create_cart,
    get_store_settings_cached,
    tenant_cache_key,
)
from public.userauth.models import Customer


def get_site_settings(request: HttpRequest):
    """Return storefront settings with the existing cached storefront service."""
    return get_store_settings_cached(request)


def get_client_ip(request: HttpRequest) -> str:
    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    candidates = [forwarded_for, request.META.get("REMOTE_ADDR", "").strip()]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return ""


def get_or_create_cart(request: HttpRequest):
    """
    Canonical storefront cart resolver.

    It delegates to the live storefront/cart services, but also handles
    guest-to-user merge in a single place for future public views.
    """
    ensure_request_session(request)
    guest_cart = None
    if request.session.session_key:
        guest_cart = storefront_get_or_create_cart(request)

    if getattr(request.user, "is_authenticated", False):
        customer = Customer.objects.filter(
            user_id=getattr(request.user, "pk", None)
        ).first()
        if customer and guest_cart and guest_cart.customer_id != customer.id:
            merged_cart = merge_guest_cart_into_user_cart(guest_cart, customer)
            request._storefront_cart = merged_cart
            return merged_cart
    return storefront_get_or_create_cart(request)


def get_cart_item_count(request: HttpRequest) -> int:
    cache_key = None
    if getattr(request.user, "is_authenticated", False):
        cache_key = tenant_cache_key(request, f"cart_item_count:{request.user.pk}")
        cached = cache.get(cache_key)
        if cached is not None:
            return int(cached)
    count = int(get_cart_summary(request).get("item_count", 0))
    if cache_key:
        cache.set(cache_key, count, 60)
    return count


def paginate_queryset(queryset, request: HttpRequest, per_page: int = 24, page_param: str = "page"):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get(page_param, 1)
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)
    return page_obj, paginator


def build_seo_context(
    title: str,
    description: str = "",
    image_url: str | None = None,
    canonical_url: str | None = None,
) -> dict[str, Any]:
    description = (description or "").strip()
    if len(description) > 160:
        trimmed = description[:160].rsplit(" ", 1)[0].strip()
        description = trimmed or description[:160]
    return storefront_build_seo_context(
        title=title,
        description=description,
        image_url=image_url,
        canonical=canonical_url,
    )


def login_required_view(view_func: Callable):
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if getattr(request.user, "is_authenticated", False):
            return view_func(request, *args, **kwargs)
        next_url = request.get_full_path()
        return redirect(f"{reverse('tenant:login')}?next={next_url}")

    return _wrapped


def require_b2b_account(view_func: Callable):
    @wraps(view_func)
    @login_required_view
    def _wrapped(request: HttpRequest, *args, **kwargs):
        customer = Customer.objects.filter(user=request.user).select_related("b2b_account").first()
        if customer and getattr(customer, "b2b_account_id", None):
            return view_func(request, *args, **kwargs)
        messages.info(request, "Apply for a B2B account to access that workspace.")
        return redirect(reverse("b2b:application"))

    return _wrapped


def rate_limit(
    *,
    rate: int,
    per_seconds: int,
    scope: str,
    by_user: bool = True,
):
    """
    Simple Redis/cache-backed rate limiter for function-based public views.
    """

    def decorator(view_func: Callable):
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs):
            ip = get_client_ip(request) or "unknown"
            user_key = str(getattr(request.user, "pk", "")) if by_user and getattr(request.user, "is_authenticated", False) else "anon"
            window = int(time.time() // per_seconds)
            cache_key = f"ratelimit:{scope}:{window}:{ip}:{user_key}"
            current = cache.get(cache_key, 0)
            if current >= rate:
                retry_after = per_seconds - (int(time.time()) % per_seconds)
                response = HttpResponse("Too many requests. Please try again later.", status=429)
                response["Retry-After"] = str(max(retry_after, 1))
                return response
            cache.set(cache_key, int(current) + 1, per_seconds)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
