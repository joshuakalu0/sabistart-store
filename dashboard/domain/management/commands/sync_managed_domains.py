from django.core.management.base import BaseCommand

from dashboard.domain.commerce import sync_managed_domain
from dashboard.domain.models import ManagedDomain


class Command(BaseCommand):
    help = "Sync managed domains from the registrar provider."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        synced = 0
        failed = 0
        queryset = ManagedDomain.objects.select_related("provider", "provider_credential").order_by("-created_at")[: options["limit"]]
        for managed_domain in queryset:
            try:
                sync_managed_domain(managed_domain)
                synced += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(f"{managed_domain.domain_name}: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Synced {synced} managed domain(s); {failed} failed."))
