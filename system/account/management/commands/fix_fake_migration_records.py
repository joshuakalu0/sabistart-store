"""
manage.py fix_fake_migration_records --schema <schema_name>
============================================================
Removes migration records that were fake-recorded as applied but whose
DDL tables do not actually exist in the schema.

This repairs the state left by the old buggy healing function which
recorded parent migrations without actually running their SQL.

Usage
-----
    python manage.py fix_fake_migration_records --schema onboard_0468d027
    python manage.py fix_fake_migration_records --schema onboard_0468d027 --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


# Map of (app_label, migration_name) -> table that must exist for the
# migration to be considered genuinely applied.
CRITICAL_TABLE_GUARDS = {
    ("userauth", "0001_initial"): "tenant_users",
    ("pos", "0002_postransaction_authoritative_order_and_more"): "pos_catalog_items",
}


def _table_exists(schema: str, table: str) -> bool:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s LIMIT 1",
            [schema, table],
        )
        return bool(cur.fetchone())


class Command(BaseCommand):
    help = "Remove fake-recorded migration entries whose DDL tables are absent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            required=True,
            help="Tenant schema name to inspect and repair.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be deleted without making any changes.",
        )

    def handle(self, *args, **options):
        schema_name: str = options["schema"].strip().lower()
        dry_run: bool = options["dry_run"]

        if not schema_name:
            raise CommandError("--schema is required.")

        self.stdout.write(self.style.NOTICE(
            f"Checking schema '{schema_name}' for stale fake migration records..."
        ))

        removed = []
        kept = []

        for (app_label, migration_name), guard_table in CRITICAL_TABLE_GUARDS.items():
            # Check if this migration is recorded as applied
            with connection.cursor() as cur:
                cur.execute(
                    f'SELECT id FROM "{schema_name}"."django_migrations" '
                    f'WHERE app = %s AND name = %s LIMIT 1',
                    [app_label, migration_name],
                )
                row = cur.fetchone()

            if not row:
                self.stdout.write(f"  [{app_label}.{migration_name}] Not in django_migrations — skipping.")
                continue

            # Check if the guard table actually exists
            table_ok = _table_exists(schema_name, guard_table)

            if table_ok:
                kept.append((app_label, migration_name))
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [{app_label}.{migration_name}] Table '{guard_table}' EXISTS — record is legitimate, keeping."
                    )
                )
            else:
                removed.append((app_label, migration_name))
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [{app_label}.{migration_name}] Table '{guard_table}' MISSING — "
                            f"would DELETE fake record (dry-run)."
                        )
                    )
                else:
                    with connection.cursor() as cur:
                        cur.execute(
                            f'DELETE FROM "{schema_name}"."django_migrations" '
                            f'WHERE app = %s AND name = %s',
                            [app_label, migration_name],
                        )
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [{app_label}.{migration_name}] Table '{guard_table}' MISSING — "
                            f"DELETED fake record. DDL will now run properly."
                        )
                    )

        self.stdout.write("")
        if removed:
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"Dry-run: would remove {len(removed)} stale record(s). Run without --dry-run to apply."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Removed {len(removed)} stale fake record(s). "
                    f"Now run: python manage.py finish_tenant_migrations --schema {schema_name}"
                ))
        else:
            self.stdout.write(self.style.SUCCESS("No stale fake records found. Schema looks clean."))
