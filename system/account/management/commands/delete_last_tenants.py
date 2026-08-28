from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection
from system.account.models import PlatformUser, OnboardingSession
from system.core.models import Shop, Domain


class Command(BaseCommand):
    help = "Safely deletes the last N registered users and drops their Postgres schemas with CASCADE."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=3,
            help="Number of recent non-superuser accounts to delete (default: 3)",
        )

    def handle(self, *args, **options):
        count = options["count"]
        users = list(
            PlatformUser.objects.filter(is_superuser=False, is_staff=False)
            .order_by("-created_at")[:count]
        )

        if not users:
            self.stdout.write(self.style.WARNING("No non-superuser accounts found to delete."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(users)} user(s) to remove:\n"))

        for user in users:
            self.stdout.write(f"=== User: {user.email} (ID: {user.id}) ===")
            
            # Find and drop any shops owned by this user
            shops = list(Shop.objects.filter(owner=user))
            for shop in shops:
                schema = shop.schema_name
                if schema and schema not in ("public", "shared", "information_schema", "pg_catalog"):
                    self.stdout.write(f"  - Dropping Postgres schema '{schema}' (CASCADE)...")
                    with connection.cursor() as cursor:
                        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
                    self.stdout.write(self.style.SUCCESS(f"    Schema '{schema}' dropped."))

                Domain.objects.filter(tenant=shop).delete()
                shop.delete()
                self.stdout.write(f"  - Shop record '{shop.name}' and domains deleted.")

            # Clean up any related onboarding sessions
            OnboardingSession.objects.filter(email__iexact=user.email).delete()

            user_email = user.email
            user.delete()
            self.stdout.write(self.style.SUCCESS(f"  - User '{user_email}' deleted successfully.\n"))

        # Also find any dangling schemas starting with onboard_ that don't belong to active shops
        with connection.cursor() as cursor:
            cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'onboard_%';")
            dangling_schemas = [row[0] for row in cursor.fetchall()]

        active_schemas = set(Shop.objects.values_list("schema_name", flat=True))
        for schema in dangling_schemas:
            if schema not in active_schemas:
                self.stdout.write(f"  - Dropping orphaned schema '{schema}'...")
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
                self.stdout.write(self.style.SUCCESS(f"    Orphaned schema '{schema}' dropped."))

        self.stdout.write(self.style.SUCCESS("Cleanup completed successfully!"))
