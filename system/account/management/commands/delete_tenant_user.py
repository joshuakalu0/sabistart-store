from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from system.account.models import PlatformUser, OnboardingSession
from system.core.models import Shop, Domain


class Command(BaseCommand):
    help = (
        "Fully deletes a tenant user by email or username — "
        "drops their Postgres schema(s), domains, onboarding sessions, and user record."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "identifier",
            type=str,
            help="Email address OR username (partial match supported with --partial)",
        )
        parser.add_argument(
            "--partial",
            action="store_true",
            default=False,
            help="Match identifier as a case-insensitive substring of email/username",
        )
        parser.add_argument(
            "--drop-orphans",
            action="store_true",
            default=True,
            help="Also drop any orphaned onboard_* schemas not tied to an active shop (default: True)",
        )

    def handle(self, *args, **options):
        # Always run in the public schema — platform_users lives there
        from django.db import connection
        try:
            with connection.cursor() as cursor:
                cursor.execute('SET search_path = "public";')
        except Exception:
            pass
        connection.set_schema_to_public()

        identifier = options["identifier"].strip()
        partial = options["partial"]

        if partial:
            users = list(
                PlatformUser.objects.filter(email__icontains=identifier)
            )
        else:
            users = list(
                PlatformUser.objects.filter(email__iexact=identifier)
            )

        if not users:
            raise CommandError(
                f"No user found matching '{identifier}'. "
                f"Try --partial for substring matching."
            )

        self.stdout.write(
            self.style.WARNING(f"\nFound {len(users)} user(s) matching '{identifier}':\n")
        )
        for u in users:
            self.stdout.write(f"  • {u.email} (id={u.id}, superuser={u.is_superuser})")

        self.stdout.write("")

        for user in users:
            self.stdout.write(
                self.style.HTTP_INFO(f"=== Deleting user: {user.email} (ID: {user.id}) ===")
            )

            # 1. Drop all owned shops and their Postgres schemas
            shops = list(Shop.objects.filter(owner=user))
            if not shops:
                self.stdout.write("  (no shops found for this user)")
            for shop in shops:
                schema = shop.schema_name
                self.stdout.write(f"  • Shop: '{shop.name}' (schema='{schema}')")

                if schema and schema not in (
                    "public", "shared", "information_schema", "pg_catalog", "pg_toast"
                ):
                    self.stdout.write(f"    – Dropping Postgres schema '{schema}' CASCADE...")
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;'
                        )
                    self.stdout.write(self.style.SUCCESS(f"    ✓ Schema '{schema}' dropped."))

                deleted_domains, _ = Domain.objects.filter(tenant=shop).delete()
                self.stdout.write(f"    – Deleted {deleted_domains} domain record(s).")
                shop.delete()
                self.stdout.write(f"    – Shop record deleted.")

            # 2. Delete all onboarding sessions for this email
            sessions_deleted, _ = OnboardingSession.objects.filter(
                email__iexact=user.email
            ).delete()
            self.stdout.write(
                f"  • Deleted {sessions_deleted} onboarding session(s)."
            )

            # 3. Delete the user
            email_snapshot = user.email
            user.delete()
            self.stdout.write(
                self.style.SUCCESS(f"  ✓ User '{email_snapshot}' permanently deleted.\n")
            )

        # 4. Drop any orphaned onboard_* schemas not tied to an active shop
        if options.get("drop_orphans", True):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'onboard_%';"
                )
                orphan_schemas = [row[0] for row in cursor.fetchall()]

            active_schemas = set(Shop.objects.values_list("schema_name", flat=True))
            dropped = 0
            for schema in orphan_schemas:
                if schema not in active_schemas:
                    self.stdout.write(
                        f"  • Dropping orphaned schema '{schema}'..."
                    )
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;'
                        )
                    self.stdout.write(
                        self.style.SUCCESS(f"    ✓ Orphaned schema '{schema}' dropped.")
                    )
                    dropped += 1

            if dropped:
                self.stdout.write(
                    self.style.SUCCESS(f"\nDropped {dropped} orphaned schema(s).")
                )

        self.stdout.write(self.style.SUCCESS("\n✓ Cleanup completed successfully!"))
