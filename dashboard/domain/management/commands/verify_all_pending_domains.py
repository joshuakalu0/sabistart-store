from django.core.management.base import BaseCommand

from dashboard.domain.tasks import poll_pending_domains


class Command(BaseCommand):
    help = "Queue verification for all pending or checking custom domains."

    def handle(self, *args, **options):
        result = poll_pending_domains()
        self.stdout.write(self.style.SUCCESS(f"Queued verification for {result.get('count', 0)} domain(s)."))
