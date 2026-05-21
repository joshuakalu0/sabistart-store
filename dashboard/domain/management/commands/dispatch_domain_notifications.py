from django.core.management.base import BaseCommand

from dashboard.domain.commerce import dispatch_domain_notifications


class Command(BaseCommand):
    help = "Create tenant-facing expiry, renewal, and connection notifications for domains."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        created = dispatch_domain_notifications(days=options["days"])
        self.stdout.write(self.style.SUCCESS(f"Created {created} domain notification(s)."))
