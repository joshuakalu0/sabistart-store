"""
manage.py repair_public_migrations
===================================
Repairs the PUBLIC schema's django_migrations table.

1. Deletes phantom rows for tenant-only apps (cart, product, pos, etc.) from public.django_migrations.
2. Deletes records for migrations that do not exist on disk in the current codebase (e.g. from newer commits rolled back).
3. Deduplicates any duplicate (app, name) records in public.django_migrations.
"""

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = "Clean up phantom tenant-app records and unknown migrations from public.django_migrations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show records that would be removed without deleting them.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        shared_app_labels = self._get_shared_app_labels()
        tenant_only_app_labels = self._get_tenant_only_app_labels(shared_app_labels)

        self.stdout.write(f"Shared app labels: {sorted(shared_app_labels)}")
        self.stdout.write(f"Tenant-only labels: {sorted(tenant_only_app_labels)}")

        loader = MigrationLoader(connection, ignore_no_migrations=True)
        disk_migrations = set(loader.disk_migrations.keys())

        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public;")

            # 1. Delete phantom tenant-only migrations from public.django_migrations
            if tenant_only_app_labels:
                placeholders = ", ".join(["%s"] * len(tenant_only_app_labels))
                cursor.execute(
                    f"SELECT id, app, name FROM public.django_migrations WHERE app IN ({placeholders}) ORDER BY app, name;",
                    list(tenant_only_app_labels),
                )
                phantom_rows = cursor.fetchall()
                if phantom_rows:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Found {len(phantom_rows)} phantom tenant-app migration rows in public schema:"
                        )
                    )
                    for r in phantom_rows:
                        self.stdout.write(f"  - [{r[1]}] {r[2]} (id={r[0]})")
                    if not dry_run:
                        cursor.execute(
                            f"DELETE FROM public.django_migrations WHERE app IN ({placeholders});",
                            list(tenant_only_app_labels),
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Deleted {cursor.rowcount} phantom tenant-app rows from public."
                            )
                        )
                else:
                    self.stdout.write("No phantom tenant-app rows found in public.")

            # 2. Delete migrations recorded in DB that do not exist on disk
            cursor.execute("SELECT id, app, name FROM public.django_migrations ORDER BY app, name;")
            all_records = cursor.fetchall()
            unknown_ids = []
            for record_id, app, name in all_records:
                if (app, name) not in disk_migrations:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Recorded migration {app}.{name} (id={record_id}) does not exist on disk."
                        )
                    )
                    unknown_ids.append(record_id)

            if unknown_ids:
                if not dry_run:
                    placeholders = ", ".join(["%s"] * len(unknown_ids))
                    cursor.execute(
                        f"DELETE FROM public.django_migrations WHERE id IN ({placeholders});",
                        unknown_ids,
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Deleted {cursor.rowcount} non-existent migration records from public."
                        )
                    )
            else:
                self.stdout.write("All recorded public migrations exist on disk.")

            # 3. Deduplicate (app, name) in public
            cursor.execute(
                """
                SELECT app, name, COUNT(*)
                FROM public.django_migrations
                GROUP BY app, name
                HAVING COUNT(*) > 1;
                """
            )
            dups = cursor.fetchall()
            if dups:
                self.stdout.write(self.style.WARNING(f"Found {len(dups)} duplicated migrations."))
                for app_name, mig_name, count in dups:
                    if not dry_run:
                        cursor.execute(
                            """
                            DELETE FROM public.django_migrations
                            WHERE id NOT IN (
                                SELECT MIN(id)
                                FROM public.django_migrations
                                WHERE app = %s AND name = %s
                            )
                            AND app = %s AND name = %s;
                            """,
                            [app_name, mig_name, app_name, mig_name],
                        )
                        self.stdout.write(f"  - Deduplicated {app_name}.{mig_name} (kept 1 of {count})")
            else:
                self.stdout.write("No duplicate migration records found.")

            # 4. Summary of remaining migrations in public
            cursor.execute(
                """
                SELECT app, COUNT(*)
                FROM public.django_migrations
                GROUP BY app
                ORDER BY app;
                """
            )
            summary = cursor.fetchall()
            self.stdout.write("\nRemaining public schema migrations by app:")
            for app, count in summary:
                self.stdout.write(f"  - {app}: {count}")

        self.stdout.write(self.style.SUCCESS("\nRepair completed successfully!"))

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
