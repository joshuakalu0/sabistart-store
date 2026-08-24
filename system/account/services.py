"""
system/account/services.py
=========================
Business logic services for platform-level operations.

These services handle:
- Tenant creation (shop setup with schema, domain)
- Tenant migration setup
"""

from django.db import connection, transaction
from django_tenants.utils import schema_context, get_tenant_domain_model

from system.core.models import Shop, Domain
from system.account.models import PlatformUser


class TenantCreationError(Exception):
    """Raised when tenant creation fails."""
    pass


class TenantService:
    """
    Service for creating and managing tenant shops.

    This service handles:
    1. Creating the Shop (tenant) record
    2. Creating the default Domain
    3. Running migrations for the new tenant schema
    """

    @staticmethod
    def create_tenant(
        owner: PlatformUser,
        name: str,
        subdomain: str,
        schema_name: str = "",
    ) -> tuple[Shop, Domain]:
        """
        Create a new tenant (shop) for a platform user.

        Args:
            owner: The PlatformUser who will own this shop
            name: Display name for the shop
            subdomain: The subdomain part of the shop URL
            schema_name: Optional schema name (defaults to subdomain)

        Returns:
            tuple of (Shop, Domain)

        Raises:
            TenantCreationError: If creation fails
        """
        subdomain = subdomain.lower()
        schema_name = (schema_name or "").strip() or subdomain

        if Domain.objects.filter(domain__iexact=subdomain).exists():
            raise TenantCreationError(
                f"The subdomain '{subdomain}' is already taken. "
                "Please choose a different one."
            )

        try:
            with transaction.atomic():
                shop = Shop.objects.create(
                    owner=owner,
                    name=name,
                    schema_name=schema_name,
                )
                domain = Domain.objects.create(
                    domain=subdomain,
                    tenant=shop,
                    is_primary=True,
                )
                return shop, domain
        except Exception as e:
            raise TenantCreationError(f"Failed to create tenant: {str(e)}")

    @staticmethod
    def run_tenant_migrations(schema_name: str) -> None:
        """
        Run all tenant migrations for a specific schema.

        This should be called after creating a new tenant schema.

        Args:
            schema_name: The tenant's schema name
        """
        from django.core.management import call_command
        from django.db import connection

        # Save the current schema
        original_schema = connection.schema_name

        try:
            # Set the tenant schema
            connection.set_tenant_schema(schema_name)

            # Run migrations for tenant apps
            # Note: In production, this might be done via Celery/async
            # to avoid blocking the request
            call_command(
                'migrate',
                schema_name=schema_name,
                run_syncdb=True,
                verbosity=0,
            )
        finally:
            # Restore the original schema
            connection.set_tenant_schema(original_schema)

    @staticmethod
    def get_tenant_for_subdomain(subdomain: str) -> Shop | None:
        """
        Get a tenant by its subdomain.

        Args:
            subdomain: The subdomain to look up

        Returns:
            Shop instance or None if not found
        """
        subdomain = subdomain.lower()
        try:
            domain = Domain.objects.select_related('tenant').get(
                domain=subdomain,
                is_primary=True,
            )
            return domain.tenant
        except Domain.DoesNotExist:
            return None

    @staticmethod
    def is_subdomain_available(subdomain: str) -> bool:
        """
        Check if a subdomain is available.

        Args:
            subdomain: The subdomain to check

        Returns:
            True if available, False if taken
        """
        subdomain = subdomain.lower()
        reserved = {'www', 'admin', 'mail', 'ftp', 'localhost', 'api',
                    'blog', 'shop', 'store', 'platform', 'public', 'private'}
        if subdomain in reserved:
            return False
        return not Domain.objects.filter(domain=subdomain).exists()
