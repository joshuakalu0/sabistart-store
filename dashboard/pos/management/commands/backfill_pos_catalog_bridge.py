from django.core.management.base import BaseCommand

from dashboard.pos.models import POSCatalogItem, POSProduct, StoreInventory
from dashboard.pos.services import sync_catalog_bridge


class Command(BaseCommand):
    help = "Create POS catalog bridge items from the real product catalog and map matching legacy inventory by SKU."

    def add_arguments(self, parser):
        parser.add_argument(
            "--published-only",
            action="store_true",
            help="Only create bridge items for published products.",
        )
        parser.add_argument(
            "--include-all-active",
            action="store_true",
            help="Bridge every active catalog product instead of only products explicitly marked as POS-ready.",
        )

    def handle(self, *args, **options):
        sync_summary = sync_catalog_bridge(
            published_only=options["published_only"],
            include_all_active=options["include_all_active"],
        )
        linked_inventory = 0
        for catalog_item in POSCatalogItem.objects.select_related("product", "variant").order_by("product__name", "variant__sku"):
            primary_sku = catalog_item.variant.sku if catalog_item.variant else catalog_item.product.sku
            fallback_sku = catalog_item.product.sku if catalog_item.variant else ""
            linked_inventory += self._link_matching_inventory(primary_sku, fallback_sku, catalog_item)

        self.stdout.write(
            self.style.SUCCESS(
                "POS catalog bridge synced. "
                f"Created {sync_summary['created_items']} catalog item(s), "
                f"updated {sync_summary['updated_items']} existing bridge item(s), "
                f"and linked {linked_inventory} inventory row(s)."
            )
        )

    def _link_matching_inventory(self, primary_sku: str, fallback_sku: str, catalog_item: POSCatalogItem) -> int:
        sku_candidates = [value for value in {primary_sku, fallback_sku} if value]
        if not sku_candidates:
            return 0

        legacy_products = POSProduct.objects.filter(sku__in=sku_candidates)
        updated = 0
        for legacy_product in legacy_products:
            updated += StoreInventory.objects.filter(
                product=legacy_product,
                catalog_item__isnull=True,
            ).update(catalog_item=catalog_item)
        return updated
