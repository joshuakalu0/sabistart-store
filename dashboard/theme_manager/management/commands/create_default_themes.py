from django.core.management.base import BaseCommand

from system.theme_marketplace.services import sync_theme_catalog

class Command(BaseCommand):
    help = "Deprecated compatibility wrapper for built-in shared theme synchronization."

    def handle(self, *args, **options):
        result = sync_theme_catalog(actor=None, bootstrap_access=True)
        self.stdout.write(
            self.style.WARNING(
                "create_default_themes is deprecated. "
                "Use manage.py sync_theme_catalog instead."
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Synced shared theme catalog: "
                f"{result['created']} created, "
                f"{result['updated']} updated, "
                f"{result['pages_synced']} pages synced, "
                f"{result['bootstrap_activated']} tenant theme(s) activated, "
                f"{result['bootstrap_already_active']} already active, "
                f"{result['bootstrap_failed']} failed."
            )
        )
