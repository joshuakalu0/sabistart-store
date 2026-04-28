from django.core.management.base import BaseCommand
from django.db import transaction

from system.system_pay.services import rebuild_payment_projections


class Command(BaseCommand):
    help = "Rebuild public platform payment projections from tenant payment schemas."

    def add_arguments(self, parser):
        parser.add_argument("--schema", dest="schema_name",
                            help="Optional tenant schema name to sync.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate projection rebuild work without committing any changes.",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            synced = rebuild_payment_projections(
                schema_name=options.get("schema_name"))
            if options.get("dry_run"):
                transaction.set_rollback(True)
        action_label = "Would sync" if options.get("dry_run") else "Synced"
        self.stdout.write(self.style.SUCCESS(
            f"{action_label} payment projections for {synced} tenant schema(s)."))
