"""
management/commands/seed_tenant_defaults.py
==========================================
Retroactively seed default theme and singleton settings for all existing
tenant schemas that are already READY but were provisioned before the
automatic seeding was added.

Usage:
    # Seed all READY tenants that are missing the default theme
    python manage.py seed_tenant_defaults

    # Seed specific schemas
    python manage.py seed_tenant_defaults --schemas abys testshop

    # Force re-seed even if theme already active
    python manage.py seed_tenant_defaults --force

    # Dry run: show what would be done
    python manage.py seed_tenant_defaults --dry-run
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from system.core.models import Shop

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Seed default theme and singleton settings for existing tenant schemas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schemas",
            nargs="*",
            metavar="SCHEMA",
            help="Specific schema names to seed. Defaults to all READY tenants.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Re-seed even if the default theme is already active.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be done without making changes.",
        )

    def handle(self, *args, **options):
        schemas_arg = options.get("schemas") or []
        force = options["force"]
        dry_run = options["dry_run"]

        if schemas_arg:
            shops = list(
                Shop.objects.filter(schema_name__in=schemas_arg).exclude(schema_name="public")
            )
        else:
            shops = list(
                Shop.objects.filter(
                    provisioning_status=Shop.ProvisioningStatus.READY
                ).exclude(schema_name="public")
            )

        if not shops:
            self.stdout.write(self.style.WARNING("No matching tenant schemas found."))
            return

        self.stdout.write(
            self.style.NOTICE(
                f"{'[DRY-RUN] ' if dry_run else ''}Seeding {len(shops)} tenant(s)..."
            )
        )

        from system.theme_marketplace.services import has_active_theme_for_schema

        seeded = 0
        skipped = 0
        failed = 0

        for shop in shops:
            schema_name = shop.schema_name
            already_active = has_active_theme_for_schema(schema_name)

            if already_active and not force:
                self.stdout.write(
                    f"  ↳ {schema_name}: theme already active — skipping "
                    f"(use --force to re-seed)."
                )
                skipped += 1
                continue

            self.stdout.write(f"  ↳ {schema_name}: seeding defaults...")

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(f"    [DRY-RUN] Would seed theme + settings.")
                )
                seeded += 1
                continue

            try:
                from system.account.migration_runner import _seed_tenant_defaults
                _seed_tenant_defaults(schema_name)
                self.stdout.write(self.style.SUCCESS(f"    ✓ Done."))
                seeded += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"    ✗ Failed: {exc}"))
                failed += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY-RUN] ' if dry_run else ''}Completed: "
                f"{seeded} seeded, {skipped} skipped, {failed} failed."
            )
        )
