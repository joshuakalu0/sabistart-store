from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django_tenants.utils import get_public_schema_name

from system.core.models import Shop
from system.feature_marketplace.services import sync_feature_entitlement_index


class Command(BaseCommand):
    help = "Rebuild the public feature entitlement index from tenant entitlements."

    def add_arguments(self, parser):
        parser.add_argument("--schema", dest="schema_name", help="Optional tenant schema name to sync.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate index rebuild work without committing any changes.",
        )

    def handle(self, *args, **options):
        queryset = Shop.objects.exclude(schema_name=get_public_schema_name()).order_by("schema_name")
        schema_name = options.get("schema_name")
        if schema_name:
            queryset = queryset.filter(schema_name=schema_name)

        total_rows = 0
        synced_tenants = 0
        skipped = 0
        for shop in queryset:
            try:
                with transaction.atomic():
                    rows = sync_feature_entitlement_index(shop)
                    total_rows += rows
                    synced_tenants += 1
                    if options.get("dry_run"):
                        transaction.set_rollback(True)
            except (OperationalError, ProgrammingError) as exc:
                skipped += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"Skipped schema '{shop.schema_name}' during entitlement index sync: {exc}"
                    )
                )

        action_label = "Would sync" if options.get("dry_run") else "Synced"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action_label} feature entitlement index for {synced_tenants} tenant schema(s); {total_rows} row(s) rebuilt."
            )
        )
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {skipped} schema(s) that are missing required tables."))
