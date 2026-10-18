"""
manage.py reset_tenant_migrations --schema <schema_name>
==========================================================
Wipes ALL django_migrations records for a tenant schema, then runs
migrate_schemas to apply all migrations cleanly from scratch.

Use this when a tenant schema's migration history is corrupted
(e.g. migrations recorded out of order, before their dependencies).

The DDL tables (actual DB tables) are NOT dropped — only the migration
history records are cleared so Django can replay them in the correct order.

Usage
-----
    python manage.py reset_tenant_migrations --schema onboard_0468d027

    # Preview what would happen without making changes:
    python manage.py reset_tenant_migrations --schema onboard_0468d027 --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection


class Command(BaseCommand):
    help = "Wipes corrupted migration history for a tenant schema and re-applies all migrations cleanly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            required=True,
            metavar="SCHEMA_NAME",
            help="The tenant schema name to reset (e.g. onboard_0468d027).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without making any changes.",
        )
        parser.add_argument(
            "--no-finalize",
            action="store_true",
            help="Skip post-migration finalisation (READY flip, admin user, etc.).",
        )

    def handle(self, *args, **options):
        from system.core.models import Shop
        from system.account.schema_inspector import (
            get_tenant_migration_status,
            invalidate_tenant_ready_cache,
        )

        schema_name: str = options["schema"].strip().lower()
        dry_run: bool = options["dry_run"]
        no_finalize: bool = options["no_finalize"]

        # Safety check
        if schema_name in ("public", "shared", "information_schema", "pg_catalog", "pg_toast"):
            raise CommandError(f"Refusing to reset protected system schema '{schema_name}'.")

        # Verify schema exists in DB
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s LIMIT 1",
                [schema_name],
            )
            if not cur.fetchone():
                raise CommandError(f"Schema '{schema_name}' does not exist in the database.")

        # Count existing migration records
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f'SELECT COUNT(*) FROM "{schema_name}"."django_migrations"',
                )
                record_count = cur.fetchone()[0]
        except Exception:
            record_count = 0

        self.stdout.write(self.style.NOTICE(
            f"\nSchema: {schema_name}"
        ))
        self.stdout.write(self.style.NOTICE(
            f"Found {record_count} migration record(s) in {schema_name}.django_migrations"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\nDry-run: would DELETE all {record_count} records from "
                f'"{schema_name}".django_migrations, then run migrate_schemas to reapply everything.'
            ))
            self.stdout.write(self.style.WARNING("No changes made. Remove --dry-run to proceed."))
            return

        # Confirm with a warning
        self.stdout.write(self.style.WARNING(
            f"\nClearing {record_count} migration record(s) from {schema_name}.django_migrations ..."
        ))

        # Step 1: Wipe all migration records for this schema
        with connection.cursor() as cur:
            cur.execute(f'DELETE FROM "{schema_name}"."django_migrations"')
        self.stdout.write(self.style.SUCCESS(
            f"✓ Cleared migration history for schema '{schema_name}'."
        ))

        # Step 2: Run migrate_schemas to reapply all migrations cleanly
        self.stdout.write(self.style.NOTICE(
            f"\nRunning migrate_schemas --tenant --schema={schema_name} ..."
        ))
        try:
            # Mark shop as IN_PROGRESS
            try:
                shop = Shop.objects.get(schema_name=schema_name)
                shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
                shop.provisioning_error = ""
                shop.save(update_fields=["provisioning_status", "provisioning_error"])
            except Shop.DoesNotExist:
                shop = None

            call_command(
                "migrate_schemas",
                schema=schema_name,
                tenant=True,
                interactive=False,
                verbosity=1,
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ migrate_schemas failed: {e}"))
            if shop:
                shop.refresh_from_db()
                shop.provisioning_status = Shop.ProvisioningStatus.FAILED
                shop.provisioning_error = str(e)[:2900]
                shop.save(update_fields=["provisioning_status", "provisioning_error"])
            return

        # Step 3: Verify
        invalidate_tenant_ready_cache(schema_name)
        try:
            status = get_tenant_migration_status(schema_name, use_cache=False)
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ [{schema_name}] Migrations complete: "
                f"{status['applied_count']}/{status['total_migrations']} applied."
            ))
        except Exception:
            pass

        # Step 4: Finalise
        if shop and not no_finalize:
            self._finalise(shop, schema_name)

    # ------------------------------------------------------------------
    def _finalise(self, shop, schema_name: str) -> None:
        """Entitlements → tenant admin user → seed defaults → READY → mark session complete."""

        # 1. Entitlements
        try:
            from system.account.models import OnboardingSession
            from system.account.services import TenantService
            session = (
                OnboardingSession.objects.filter(metadata__tenant_schema_name=schema_name)
                .exclude(status__in=[
                    OnboardingSession.Status.COMPLETED,
                    OnboardingSession.Status.CANCELLED,
                ])
                .order_by("-updated_at")
                .first()
            )
            if session:
                TenantService.provision_tenant_entitlements(session, shop)
                self.stdout.write(self.style.SUCCESS(f"  ✓ [{schema_name}] Entitlements provisioned."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Entitlements (non-fatal): {e}"))

        # 2. Tenant admin user
        try:
            from system.account.sso import ensure_tenant_admin_user
            ensure_tenant_admin_user(shop, shop.owner)
            self.stdout.write(self.style.SUCCESS(f"  ✓ [{schema_name}] Tenant admin user created/updated."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Tenant admin user (non-fatal): {e}"))

        # 3. Seed defaults
        try:
            from system.account.migration_runner import _seed_tenant_defaults
            _seed_tenant_defaults(schema_name)
            self.stdout.write(self.style.SUCCESS(f"  ✓ [{schema_name}] Defaults seeded."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Defaults seeding (non-fatal): {e}"))

        # 4. Flip to READY
        try:
            from system.account.migration_runner import _finalize_ready
            _finalize_ready(shop)
            self.stdout.write(self.style.SUCCESS(f"  ✓ [{schema_name}] Status → READY."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Could not flip to READY: {e}"))

        # 5. Mark onboarding session completed
        try:
            from django.utils import timezone
            from system.account.models import OnboardingSession
            session = (
                OnboardingSession.objects.filter(metadata__tenant_schema_name=schema_name)
                .exclude(status__in=[
                    OnboardingSession.Status.COMPLETED,
                    OnboardingSession.Status.CANCELLED,
                ])
                .order_by("-updated_at")
                .first()
            )
            if session:
                metadata = dict(session.metadata or {})
                metadata["provisioned_at"] = timezone.now().isoformat()
                metadata["provisioning_source"] = "reset_tenant_migrations_cmd"
                session.status = OnboardingSession.Status.COMPLETED
                session.completed_at = timezone.now()
                session.metadata = metadata
                session.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ [{schema_name}] Onboarding session marked COMPLETED."
                ))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Onboarding session (non-fatal): {e}"))
