from django.core.management.base import BaseCommand

from system.theme_marketplace.services import sync_theme_catalog


class Command(BaseCommand):
    help = "Synchronize the built-in shared theme catalog from themes/<slug>/theme.json manifests."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-bootstrap-access",
            action="store_true",
            help="Skip automatic access bootstrap for existing shops.",
        )

    def handle(self, *args, **options):
        result = sync_theme_catalog(
            actor=None,
            bootstrap_access=not options["no_bootstrap_access"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Synced shared theme catalog: "
                f"{result['created']} created, "
                f"{result['updated']} updated, "
                f"{result['category_created']} categories created, "
                f"{result['pages_synced']} pages synced."
            )
        )
