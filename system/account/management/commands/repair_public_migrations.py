"""
manage.py repair_public_migrations
===================================
One-off repair for the public schema's django_migrations table.

During previous runs or worker execution, tenant-app migration records
were written into the PUBLIC schema's django_migrations table (they
never belong in the public schema -- tenant apps live in per-tenant schemas).
Those phantom rows cause ``InconsistentMigrationHistory`` errors that block
`migrate --schema=public`.

This command:
  1. Identifies tenant-only apps vs shared apps using SHARED_APPS / TENANT_APPS.
  2. Deletes from the PUBLIC schema's django_migrations table any rows for apps
     that are tenant-only.
  3. Removes duplicate (app, name) rows in the public schema.
  4. Detects stranded initial migrations for shared apps whose tables exist on
     disk but lack records in django_migrations, and marks them applied.

Safe to run any number of times.
"""
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


_KNOWN_INITIAL_TABLE_MAP = {
    ("system_feature_marketplace", "0001_initial"): "system_feature_marketplace_featurebundle",
    ("core", "0001_initial"): "core_shop",
    ("account", "0001_initial"): "account_platformuser",
    ("system_pay", "0001_initial"): "system_pay_platformpaymentsetting",
}


class Command(BaseCommand):
    help = (
        "Remove phantom tenant-app migration records and duplicates from the "
        "PUBLIC schema's django_migrations table (fixes InconsistentMigrationHistory)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be cleaned up without modifying the database.",
        )
        parser.add_argument(
            "--fake-stranded",
            action="store_true",
            default=True,
            help="Fake-apply initial migrations for shared apps if tables already exist.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        fake_stranded = options["fake_stranded"]

        shared_app_labels = self._get_shared_app_labels()
        tenant_only_app_labels = self._get_tenant_only_app_labels(shared_app_labels)

        self.stdout.write(f"Shared apps : {sorted(shared_app_labels)}")
        self.stdout.write(f"Tenant-only : {sorted(tenant_only_app_labels)}")

        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public;")

            # 1. Delete phantom tenant-only app migrations from public schema
            if tenant_only_app_labels:
                placeholders = ", ".join(["%s"] * len(tenant_only_app_labels))
                if dry_run:
                    cursor.execute(
                        f"SELECT id, app, name FROM public.django_migrations WHERE app IN ({placeholders}) ORDER BY app, name;",
                        list(tenant_only_app_labels),
                    )
                    rows = cursor.fetchall()
                    self.stdout.write(self.style.WARNING(f"[Dry Run] Found {len(rows)} phantom tenant-app rows in public:"))
                    for r in rows:
                        self.stdout.write(f"  - id={r[0]} {r[1]}.{r[2]}")
                else:
                    cursor.execute(
                        f"DELETE FROM public.django_migrations WHERE app IN ({placeholders});",
                        list(tenant_only_app_labels),
                    )
                    deleted_count = cursor.rowcount
                    self.stdout.write(self.style.SUCCESS(f"Removed {deleted_count} phantom tenant-app rows from public schema."))

            # 2. Deduplicate any (app, name) records in public
            cursor.execute("""
                SELECT app, name, COUNT(*)
                FROM public.django_migrations
                GROUP BY app, name
                HAVING COUNT(*) > 1;
            """)
            dup_groups = cursor.fetchall()
            if dup_groups:
                self.stdout.write(f"Found {len(dup_groups)} duplicate migration entries.")
                for app_name, mig_name, count in dup_groups:
                    if not dry_run:
                        cursor.execute("""
                            DELETE FROM public.django_migrations
                            WHERE id NOT IN (
                                SELECT MIN(id)
                                FROM public.django_migrations
                                WHERE app = %s AND name = %s
                            )
                            AND app = %s AND name = %s;
                        """, [app_name, mig_name, app_name, mig_name])
                        self.stdout.write(f"  - Deduplicated {app_name}.{mig_name} (kept 1 of {count})")

            # 3. Stranded initial check
            if fake_stranded and not dry_run:
                self._fake_stranded_initials(cursor)

            # 4. Summary of remaining rows in public.django_migrations
            cursor.execute("""
                SELECT app, count(*) 
                FROM public.django_migrations 
                GROUP BY app 
                ORDER BY app;
            """)
            remaining = cursor.fetchall()
            self.stdout.write("\nRemaining public schema migration apps:")
            for app_label, count in remaining:
                self.stdout.write(f"  {app_label}: {count}")

        self.stdout.write(self.style.SUCCESS("\nPublic migrations repair complete!"))

    def _get_shared_app_labels(self) -> set[str]:
        labels = set()
        for app_spec in settings.SHARED_APPS:
            try:
                app_config = apps.get_app_config(app_spec.split(".")[-1])
                labels.add(app_config.label)
            except Exception:
                labels.add(app_spec.split(".")[-1])
        return labels

    def _get_tenant_only_app_labels(self, shared_labels: set[str]) -> set[str]:
        tenant_labels = set()
        for app_spec in settings.TENANT_APPS:
            try:
                app_config = apps.get_app_config(app_spec.split(".")[-1])
                label = app_config.label
            except Exception:
                label = app_spec.split(".")[-1]
            if label not in shared_labels:
                tenant_labels.add(label)
        return tenant_labels

    def _fake_stranded_initials(self, cursor):
        for (app_label, migration_name), sentinel_table in _KNOWN_INITIAL_TABLE_MAP.items():
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                );
                """,
                [sentinel_table],
            )
            table_exists = cursor.fetchone()[0]
            if not table_exists:
                continue

            cursor.execute(
                "SELECT 1 FROM public.django_migrations WHERE app = %s AND name = %s LIMIT 1;",
                [app_label, migration_name],
            )
            recorded = cursor.fetchone()
            if not recorded:
                self.stdout.write(f"Fake-applying stranded initial migration {app_label}.{migration_name}...")
                cursor.execute(
                    "INSERT INTO public.django_migrations (app, name, applied) VALUES (%s, %s, %s);",
                    [app_label, migration_name, timezone.now()],
                )
