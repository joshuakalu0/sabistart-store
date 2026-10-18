"""
manage.py finish_tenant_migrations
====================================
Runs all pending tenant migrations to completion.
Can target a specific user (by email or user ID) or a specific schema name,
or all pending tenants if no filter is given.

Usage
-----
    # Complete all pending migrations across all tenants:
    python manage.py finish_tenant_migrations

    # Complete migrations for a specific schema:
    python manage.py finish_tenant_migrations --schema onboard_ab12cd34

    # Complete migrations for all stores owned by a user (by email):
    python manage.py finish_tenant_migrations --user john@example.com

    # Complete migrations for all stores owned by a user (by ID):
    python manage.py finish_tenant_migrations --user 42

    # Dry-run: show what would be processed without making changes:
    python manage.py finish_tenant_migrations --dry-run

Exit codes
----------
0 = All specified tenants are now fully migrated (or were already ready).
1 = One or more migrations failed.
"""
from __future__ import annotations

import sys
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Completes all pending tenant schema migrations to 100%%, optionally "
        "filtered to a specific schema name or a platform user (by email or ID). "
        "After migrations finish the schema is marked READY and the tenant admin "
        "user is provisioned automatically."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            action="append",
            default=[],
            metavar="SCHEMA_NAME",
            help=(
                "Schema name(s) to migrate (repeatable). "
                "If omitted, all tenants that are not READY are processed."
            ),
        )
        parser.add_argument(
            "--user",
            metavar="EMAIL_OR_ID",
            default="",
            help=(
                "Process only the tenant(s) owned by this platform user. "
                "Accepts an email address or a numeric user ID."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print which tenants would be migrated without actually running anything.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=1,
            help="Migrations per chunk (default: 1). Increase to speed up on large RAM hosts.",
        )
        parser.add_argument(
            "--no-finalize",
            action="store_true",
            help="Skip post-migration finalisation (entitlements, admin user, READY flip).",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        from system.core.models import Shop
        from system.account.schema_inspector import (
            get_tenant_migration_status,
            invalidate_tenant_ready_cache,
        )
        from system.account.migration_runner import (
            advance_tenant_provisioning,
            ChunkedMigrationError,
        )

        dry_run: bool = options["dry_run"]
        chunk_size: int = max(1, options["chunk_size"])
        no_finalize: bool = options["no_finalize"]
        user_filter: str = options["user"].strip()
        explicit_schemas: list[str] = [
            s.strip().lower() for s in options["schema"] if s and s.strip()
        ]

        # 1. Resolve which shops to target --------------------------------
        shops_qs = Shop.objects.select_related("owner").prefetch_related("domains").order_by("created_on")

        # Filter by user
        if user_filter:
            from system.account.models import PlatformUser
            try:
                if user_filter.isdigit():
                    owner = PlatformUser.objects.get(pk=int(user_filter))
                else:
                    owner = PlatformUser.objects.get(email__iexact=user_filter)
            except PlatformUser.DoesNotExist:
                raise CommandError(
                    f"No platform user found matching '{user_filter}'. "
                    "Use --user with a valid email or numeric ID."
                )
            shops_qs = shops_qs.filter(owner=owner)
            self.stdout.write(
                self.style.NOTICE(
                    f"Filtering to stores owned by: {owner.email} (id={owner.pk})"
                )
            )

        # Filter by explicit schema names
        if explicit_schemas:
            shops_qs = shops_qs.filter(schema_name__in=explicit_schemas)

        # Only include shops that are NOT already READY (unless explicit schema given)
        if not explicit_schemas and not user_filter:
            shops_qs = shops_qs.exclude(provisioning_status=Shop.ProvisioningStatus.READY)
        elif not explicit_schemas:
            # If a user was given, still skip already-ready shops
            shops_qs = shops_qs.exclude(provisioning_status=Shop.ProvisioningStatus.READY)

        shops = list(shops_qs)

        if not shops:
            self.stdout.write(self.style.SUCCESS("✓ No pending tenant migrations found. All stores are ready."))
            return

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(shops)} store(s) to migrate: "
                + ", ".join(s.schema_name for s in shops)
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run mode: no migrations will be applied."))
            for shop in shops:
                try:
                    status = get_tenant_migration_status(shop.schema_name, use_cache=False)
                    self.stdout.write(
                        f"  [{shop.schema_name}] "
                        f"applied={status['applied_count']}/{status['total_migrations']} "
                        f"({status['progress_percent']}%) "
                        f"pending={status['pending_count']}"
                    )
                except Exception as e:
                    self.stdout.write(f"  [{shop.schema_name}] Could not inspect: {e}")
            return

        # 2. Migrate each shop ------------------------------------------
        all_ok = True

        for shop in shops:
            schema_name = shop.schema_name
            self.stdout.write("")
            self.stdout.write(
                self.style.NOTICE(
                    f"━━━ [{schema_name}] Starting migration (owner: {shop.owner.email}) ━━━"
                )
            )

            try:
                status_before = get_tenant_migration_status(schema_name, use_cache=False)
                self.stdout.write(
                    f"  Before: {status_before['applied_count']}/{status_before['total_migrations']} applied "
                    f"({status_before['progress_percent']}%), pending={status_before['pending_count']}"
                )

                if status_before["is_ready"]:
                    self.stdout.write(self.style.SUCCESS(f"  [{schema_name}] Already fully migrated. Skipping."))
                    continue

                # Flip to IN_PROGRESS
                shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
                shop.provisioning_error = ""
                shop.save(update_fields=["provisioning_status", "provisioning_error"])

                # Run advance_tenant_provisioning in a loop until complete
                max_iterations = 2000  # safety cap
                iterations = 0

                while iterations < max_iterations:
                    iterations += 1
                    invalidate_tenant_ready_cache(schema_name)

                    result = advance_tenant_provisioning(
                        schema_name,
                        time_budget=300,
                        source="finish_tenant_migrations_cmd",
                    )

                    if result.get("is_ready") or result.get("failed"):
                        break

                    # Check DB state
                    current = get_tenant_migration_status(schema_name, use_cache=False)
                    if current["is_ready"]:
                        break

                    self.stdout.write(
                        f"  [{schema_name}] Progress: "
                        f"{current['applied_count']}/{current['total_migrations']} "
                        f"({current['progress_percent']}%)"
                    )

                # Final status check
                invalidate_tenant_ready_cache(schema_name)
                status_after = get_tenant_migration_status(schema_name, use_cache=False)

                if status_after["is_ready"]:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ [{schema_name}] All {status_after['total_migrations']} migrations applied."
                        )
                    )

                    if not no_finalize:
                        self._finalise(shop, schema_name)
                else:
                    error_msg = result.get("error", "Unknown error") if result.get("failed") else "Migrations still pending after max iterations."
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ [{schema_name}] Failed: {error_msg} "
                            f"({status_after['applied_count']}/{status_after['total_migrations']} applied)"
                        )
                    )
                    shop.refresh_from_db()
                    shop.provisioning_status = Shop.ProvisioningStatus.FAILED
                    shop.provisioning_error = error_msg[:2900]
                    shop.save(update_fields=["provisioning_status", "provisioning_error"])
                    all_ok = False

            except ChunkedMigrationError as e:
                self.stdout.write(self.style.ERROR(f"  ✗ [{schema_name}] Migration error: {e}"))
                shop.refresh_from_db()
                shop.provisioning_status = Shop.ProvisioningStatus.FAILED
                shop.provisioning_error = str(e)[:2900]
                shop.save(update_fields=["provisioning_status", "provisioning_error"])
                all_ok = False

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ [{schema_name}] Unexpected error: {e}"))
                all_ok = False

        self.stdout.write("")
        if all_ok:
            self.stdout.write(self.style.SUCCESS(f"✓ All {len(shops)} tenant migration(s) completed successfully."))
        else:
            self.stdout.write(self.style.ERROR("✗ One or more tenant migrations failed. Check output above."))
            sys.exit(1)

    # ------------------------------------------------------------------
    def _finalise(self, shop, schema_name: str) -> None:
        """Run post-migration finalisation: entitlements, tenant admin user, READY status."""

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
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Entitlements failed (non-fatal): {e}"))

        # 2. Tenant admin user
        try:
            from system.account.sso import ensure_tenant_admin_user, TenantSchemaNotReady
            ensure_tenant_admin_user(shop, shop.owner)
            self.stdout.write(self.style.SUCCESS(f"  ✓ [{schema_name}] Tenant admin user created/updated."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Tenant admin user failed (non-fatal): {e}"))

        # 3. Seed defaults
        try:
            from system.account.migration_runner import _seed_tenant_defaults
            _seed_tenant_defaults(schema_name)
            self.stdout.write(self.style.SUCCESS(f"  ✓ [{schema_name}] Defaults seeded."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Defaults seeding failed (non-fatal): {e}"))

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
                metadata["provisioning_source"] = "finish_tenant_migrations_cmd"
                session.status = OnboardingSession.Status.COMPLETED
                session.completed_at = timezone.now()
                session.metadata = metadata
                session.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
                self.stdout.write(self.style.SUCCESS(f"  ✓ [{schema_name}] Onboarding session marked COMPLETED."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ [{schema_name}] Could not mark onboarding session: {e}"))
