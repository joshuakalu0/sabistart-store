from django.core.management.base import BaseCommand

from dashboard.domain.commerce import reconcile_managed_domain_integrity


class Command(BaseCommand):
    help = "Reconcile managed domain and custom-domain linkage plus provider sync state."

    def handle(self, *args, **options):
        result = reconcile_managed_domain_integrity()
        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciled {result['fixed_connections']} connection record(s) and synced {result['synced']} managed domain(s)."
            )
        )
