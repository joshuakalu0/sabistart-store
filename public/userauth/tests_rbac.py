import uuid

from django.core.management import call_command
from django.db import connection
from django_tenants.test.cases import TenantTestCase

from public.userauth.models import Permission, Role
from public.userauth.permission_registry import ALL_PERMISSION_CODENAMES, BUILT_IN_ROLE_DEFINITIONS
from system.account.models import PlatformUser


class RBACSyncTenantTestCase(TenantTestCase):
    platform_owner = None

    @classmethod
    def get_test_schema_name(cls):
        if not hasattr(cls, "_test_schema_name"):
            cls._test_schema_name = f"rbac_{uuid.uuid4().hex[:18]}"
        return cls._test_schema_name

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={
                "first_name": "RBAC",
                "last_name": "Owner",
                "account_status": PlatformUser.AccountStatus.ACTIVE,
            },
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "RBAC Test Shop"
        return tenant

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.tenant is not None:
            call_command(
                "migrate_schemas",
                schema=cls.tenant.schema_name,
                tenant=True,
                interactive=False,
                verbosity=0,
            )

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)


class StaffPermissionSyncCommandTests(RBACSyncTenantTestCase):
    def test_sync_staff_permissions_default_scope_creates_live_catalog(self):
        call_command("sync_staff_permissions", verbosity=0)

        self.assertEqual(
            Permission.objects.filter(codename__in=ALL_PERMISSION_CODENAMES, is_active=True).count(),
            len(ALL_PERMISSION_CODENAMES),
        )
        self.assertEqual(
            Role.objects.filter(is_system=True, slug__in=[role.slug for role in BUILT_IN_ROLE_DEFINITIONS]).count(),
            len(BUILT_IN_ROLE_DEFINITIONS),
        )

        owner_role = Role.objects.get(slug="owner")
        self.assertEqual(set(owner_role.get_permissions()), set(ALL_PERMISSION_CODENAMES))

    def test_sync_staff_permissions_single_schema_deactivates_stale_generated_permissions(self):
        Permission.objects.create(
            name="Legacy Permission",
            codename="legacy.old",
            description="Outdated generated permission",
            category="settings",
            is_system=True,
            is_active=True,
        )

        call_command("sync_staff_permissions", "--schema", self.tenant.schema_name, verbosity=0)

        stale = Permission.objects.get(codename="legacy.old")
        self.assertFalse(stale.is_active)

    def test_sync_staff_permissions_dry_run_does_not_write(self):
        self.assertEqual(Permission.objects.count(), 0)
        self.assertEqual(Role.objects.count(), 0)

        call_command("sync_staff_permissions", "--schema", self.tenant.schema_name, "--dry-run", verbosity=0)

        self.assertEqual(Permission.objects.count(), 0)
        self.assertEqual(Role.objects.count(), 0)

    def test_sync_staff_permissions_preserves_custom_roles(self):
        call_command("sync_staff_permissions", "--schema", self.tenant.schema_name, verbosity=0)
        custom = Role.objects.create(
            name="Night Shift",
            slug="night-shift",
            description="Custom operator role",
            is_system=False,
            role_type="custom",
        )

        call_command("sync_staff_permissions", "--schema", self.tenant.schema_name, verbosity=0)

        self.assertTrue(Role.objects.filter(pk=custom.pk, slug="night-shift").exists())

    def test_built_in_roles_follow_broad_operational_defaults(self):
        call_command("sync_staff_permissions", "--schema", self.tenant.schema_name, verbosity=0)

        owner_role = Role.objects.get(slug="owner")
        admin_role = Role.objects.get(slug="admin")
        manager_role = Role.objects.get(slug="manager")

        self.assertEqual(len(owner_role.get_permissions()), len(ALL_PERMISSION_CODENAMES))
        self.assertNotIn("domains.delete", admin_role.get_permissions())
        self.assertIn("products.view", manager_role.get_permissions())
        self.assertIn("pos.sell", manager_role.get_permissions())
        self.assertNotIn("notifications.manage_webhooks", manager_role.get_permissions())
