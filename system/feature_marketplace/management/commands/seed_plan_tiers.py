from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed the active Starter, Premium, and Pro plan packs."

    def handle(self, *args, **options):
        call_command(
            "seed_feature_catalog",
            profile="realistic-plus",
            verbosity=options.get("verbosity", 1),
        )
        self.stdout.write(self.style.SUCCESS("Starter, Premium, and Pro plan packs are ready."))
