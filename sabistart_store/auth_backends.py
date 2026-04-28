from __future__ import annotations

from django.contrib.auth.backends import BaseBackend
from django.db import connection

from public.userauth.backends import TenantAuthBackend
from system.account.backends import PlatformAuthBackend


class SchemaAwareAuthenticationBackend(BaseBackend):
    """
    Route authentication to the correct backend for the active schema.

    Public schema requests authenticate PlatformUser accounts.
    Tenant schema requests authenticate TenantUser accounts, including the
    existing platform-owner bridge handled by TenantAuthBackend.
    """

    tenant_backend = TenantAuthBackend()
    platform_backend = PlatformAuthBackend()

    def authenticate(self, request, username: str = None, password: str = None,
                     email: str = None, **kwargs):
        backend = self._select_backend(request)
        return backend.authenticate(
            request,
            username=username,
            password=password,
            email=email,
            **kwargs,
        )

    def get_user(self, user_id):
        backend = self._select_backend(None)
        return backend.get_user(user_id)

    def has_perm(self, user_obj, perm, obj=None):
        backend = self.platform_backend if self._is_platform_user(user_obj) else self.tenant_backend
        has_perm = getattr(backend, "has_perm", None)
        if callable(has_perm):
            return has_perm(user_obj, perm, obj=obj)
        return False

    def _select_backend(self, request):
        schema_name = self._get_schema_name(request)
        if schema_name and schema_name != "public":
            return self.tenant_backend
        return self.platform_backend

    @staticmethod
    def _get_schema_name(request) -> str:
        tenant = getattr(request, "tenant", None) if request is not None else None
        return (
            getattr(tenant, "schema_name", None)
            or getattr(connection, "schema_name", None)
            or "public"
        )

    @staticmethod
    def _is_platform_user(user_obj) -> bool:
        meta = getattr(user_obj, "_meta", None)
        return (
            meta is not None
            and meta.app_label == "account"
            and meta.model_name == "platformuser"
        )
