from django.core.management.base import BaseCommand

from dashboard.domain.commerce import process_paid_domain_orders


class Command(BaseCommand):
    help = "Process paid domain purchase and renewal orders."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        processed = process_paid_domain_orders(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} paid domain order(s)."))
