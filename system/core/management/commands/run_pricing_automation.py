from __future__ import annotations

from django.core.management.base import BaseCommand

from dashboard.pricing.utiles.automation import run_pricing_automation


class Command(BaseCommand):
    help = "Run cron-safe pricing automation for abandoned cart, post-purchase, win-back, milestone, birthday, and review rewards."

    def handle(self, *args, **options):
        summary = run_pricing_automation()
        self.stdout.write(self.style.SUCCESS("Pricing automation run completed."))
        for key, value in summary.as_dict().items():
            self.stdout.write(f"{key}: {value}")
