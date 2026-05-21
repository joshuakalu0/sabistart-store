from django.core.management.base import BaseCommand

from dashboard.domain.commerce import ensure_default_domain_catalog, sync_provider_tld_catalog


class Command(BaseCommand):
    help = "Sync the shared registrar TLD catalog into the platform domain workspace."

    def handle(self, *args, **options):
        provider, _ = ensure_default_domain_catalog()
        synced = sync_provider_tld_catalog(provider=provider)
        self.stdout.write(self.style.SUCCESS(f"Synced {synced} TLD catalog entries for {provider.name}."))
