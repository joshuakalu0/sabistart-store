"""
system/account/management/commands/clear_stale_migrations.py
==============================================================
Management command to clear stale migration progress and locks for a schema.

Usage:
    python manage.py clear_stale_migrations --schema <schema_name>
    python manage.py clear_stale_migrations --schema <schema_name> --force

This clears:
- Redis worker progress keys
- Redis watchdog keys
- Redis migration locks
- Redis failure cooldowns
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

REDIS_PREFIXES = [
    "worker_migration_progress",
    "celery_migration_watchdog",
    "tenant_migration_lock",
    "tenant_migration_fail_cooldown",
]


class Command(BaseCommand):
    help = "Clear stale migration progress, locks, and cooldowns for a schema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            required=True,
            help="Schema name to clear migration state for.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Clear state even if the schema is currently running.",
        )

    def handle(self, *args, **options):
        schema_name = options["schema"].strip().lower()
        force = options["force"]

        self.stdout.write(f"Clearing migration state for schema: {schema_name}")

        cleared = []
        for prefix in REDIS_PREFIXES:
            key = f"{prefix}:{schema_name}"
            try:
                existing = cache.get(key)
                if existing:
                    if not force and prefix == "worker_migration_progress":
                        status = existing.get("status", "") if isinstance(existing, dict) else ""
                        if status == "RUNNING":
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Skipping {key} (status=RUNNING). Use --force to clear anyway."
                                )
                            )
                            continue
                    cache.delete(key)
                    cleared.append(key)
                    self.stdout.write(self.style.SUCCESS(f"Cleared {key}"))
                else:
                    self.stdout.write(f"No data in {key}")
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"Failed to clear {key}: {exc}"))

        self.stdout.write(self.style.SUCCESS(f"\nCleared {len(cleared)} Redis keys for '{schema_name}'."))
        self.stdout.write("You can now re-trigger the onboarding flow to restart migrations.")
