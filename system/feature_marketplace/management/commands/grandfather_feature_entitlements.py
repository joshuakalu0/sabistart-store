from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from dashboard.feature_marketplace.services import grandfather_legacy_entitlements


class Command(BaseCommand):
    help = "Grandfather legacy feature toggles and live quota usage into marketplace entitlements."

    def add_arguments(self, parser):
        parser.add_argument("--schema", dest="schema_name", help="Optional tenant schema name to target.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate the grandfathering work without committing any changes.",
        )

    def handle(self, *args, **options):
        total = 0
        processed = 0
        skipped = 0
        TenantModel = get_tenant_model()
        queryset = TenantModel.objects.exclude(schema_name=get_public_schema_name()).order_by("schema_name")
        if options.get("schema_name"):
            queryset = queryset.filter(schema_name=options["schema_name"])
        for tenant in queryset:
            with schema_context(tenant.schema_name):
                try:
                    with transaction.atomic():
                        total += grandfather_legacy_entitlements()
                        processed += 1
                        if options.get("dry_run"):
                            transaction.set_rollback(True)
                except (OperationalError, ProgrammingError) as exc:
                    skipped += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"Skipped schema '{tenant.schema_name}' during grandfathering: {exc}"
                        )
                    )
        action_label = "Would grandfather" if options.get("dry_run") else "Grandfathered"
        self.stdout.write(self.style.SUCCESS(f"{action_label} {total} entitlement records across {processed} tenant schema(s)."))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {skipped} schema(s) that are missing required tables."))
