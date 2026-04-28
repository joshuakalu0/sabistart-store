from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from dashboard.feature_marketplace.models import TenantEntitlement
from dashboard.feature_marketplace.services import list_expiring_entitlements


class Command(BaseCommand):
    help = "Mark near-expiry entitlements as reminded so renewal nudges can be surfaced in the dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--schema", dest="schema_name", help="Optional tenant schema name to target.")
        parser.add_argument(
            "--within-days",
            dest="within_days",
            type=int,
            default=14,
            help="How many days ahead to look for expiring entitlements.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate reminder updates without committing any changes.",
        )

    def handle(self, *args, **options):
        total = 0
        TenantModel = get_tenant_model()
        queryset = TenantModel.objects.exclude(schema_name=get_public_schema_name()).order_by("schema_name")
        if options.get("schema_name"):
            queryset = queryset.filter(schema_name=options["schema_name"])
        skipped = 0
        processed = 0
        for tenant in queryset:
            with schema_context(tenant.schema_name):
                try:
                    with transaction.atomic():
                        for entitlement in list_expiring_entitlements(within_days=options["within_days"]):
                            if entitlement.reminder_sent_at:
                                continue
                            TenantEntitlement.objects.filter(pk=entitlement.pk).update(reminder_sent_at=timezone.now())
                            total += 1
                        processed += 1
                        if options.get("dry_run"):
                            transaction.set_rollback(True)
                except (OperationalError, ProgrammingError) as exc:
                    skipped += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"Skipped schema '{tenant.schema_name}' during reminder processing: {exc}"
                        )
                    )
        action_label = "Would mark" if options.get("dry_run") else "Marked"
        self.stdout.write(self.style.SUCCESS(f"{action_label} {total} entitlements for renewal reminders across {processed} tenant schema(s)."))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {skipped} schema(s) that are missing required tables."))
