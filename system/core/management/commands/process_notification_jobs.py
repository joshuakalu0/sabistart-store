from __future__ import annotations

from django.core.management.base import BaseCommand

from dashboard.pricing.utiles.automation import process_due_notification_jobs


class Command(BaseCommand):
    help = "Process queued notification jobs using the cron-safe local delivery runner."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of queued jobs to process in one run.",
        )

    def handle(self, *args, **options):
        result = process_due_notification_jobs(limit=max(1, int(options["limit"])))
        self.stdout.write(self.style.SUCCESS("Notification queue processing completed."))
        for key, value in result.items():
            self.stdout.write(f"{key}: {value}")
