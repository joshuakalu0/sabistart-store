from django.core.management.base import BaseCommand

from dashboard.domain.tasks import renew_expiring_certificates


class Command(BaseCommand):
    help = "Renew or queue renewal for SSL certificates nearing expiry."

    def handle(self, *args, **options):
        result = renew_expiring_certificates()
        self.stdout.write(self.style.SUCCESS(f"Processed {result.get('count', 0)} certificate renewal candidate(s)."))
