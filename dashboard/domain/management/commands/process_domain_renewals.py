from django.core.management.base import BaseCommand

from dashboard.domain.commerce import process_due_domain_renewals


class Command(BaseCommand):
    help = "Execute due scheduled managed-domain renewals."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        processed = process_due_domain_renewals(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} due domain renewal(s)."))
