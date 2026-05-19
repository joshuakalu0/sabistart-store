from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.pricing.models import AutomaticDiscount, DiscountCode, DiscountUsage, FlashSaleItem
from public.cart.models import Order, OrderDiscount, OrderItem


class Command(BaseCommand):
    help = "Reconcile discount usage, automatic discount counters, and flash-sale sold units from live order state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report drift without writing any fixes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        usage_report = self._reconcile_discount_usages(dry_run=dry_run)
        code_report = self._reconcile_discount_code_counters(dry_run=dry_run)
        automatic_report = self._reconcile_automatic_discount_counters(dry_run=dry_run)
        flash_report = self._reconcile_flash_sale_units(dry_run=dry_run)

        self.stdout.write(self.style.SUCCESS("Pricing reconciliation complete."))
        self.stdout.write(
            f"Discount usages updated: {usage_report['updated']} | "
            f"Discount codes fixed: {code_report['updated']} | "
            f"Automatic discounts fixed: {automatic_report['updated']} | "
            f"Flash sale items fixed: {flash_report['updated']}"
        )

    def _order_state_map(self) -> dict[str, dict]:
        order_ids = list(DiscountUsage.objects.values_list("order_id", flat=True).distinct())
        rows = Order.objects.filter(id__in=order_ids).values("id", "status", "financial_status")
        return {str(row["id"]): row for row in rows}

    @staticmethod
    def _should_reverse_from_order(row: dict | None) -> bool:
        if not row:
            return False
        return row["status"] == Order.OrderStatus.CANCELLED or row["financial_status"] == Order.FinancialStatus.VOIDED

    def _reconcile_discount_usages(self, *, dry_run: bool) -> dict[str, int]:
        updated = 0
        order_state_map = self._order_state_map()
        with transaction.atomic():
            for usage in DiscountUsage.objects.select_related("discount_code").all():
                should_be_reversed = self._should_reverse_from_order(order_state_map.get(str(usage.order_id)))
                if usage.is_reversed == should_be_reversed:
                    continue
                updated += 1
                if dry_run:
                    continue
                usage.is_reversed = should_be_reversed
                usage.reversed_at = usage.reversed_at if should_be_reversed else None
                if should_be_reversed and usage.reversed_at is None:
                    from django.utils import timezone

                    usage.reversed_at = timezone.now()
                if not should_be_reversed:
                    usage.reversal_reason = ""
                elif not usage.reversal_reason:
                    usage.reversal_reason = "reconciled_from_order_state"
                usage.save(
                    update_fields=[
                        "is_reversed",
                        "reversed_at",
                        "reversal_reason",
                    ]
                )
        return {"updated": updated}

    def _reconcile_discount_code_counters(self, *, dry_run: bool) -> dict[str, int]:
        expected = Counter(
            DiscountUsage.objects.filter(is_reversed=False).values_list("discount_code_id", flat=True)
        )
        updated = 0
        with transaction.atomic():
            for code in DiscountCode.objects.all():
                expected_count = int(expected.get(code.id, 0))
                if int(code.usage_count or 0) == expected_count:
                    continue
                updated += 1
                if not dry_run:
                    code.usage_count = expected_count
                    code.save(update_fields=["usage_count", "updated_at"])
        return {"updated": updated}

    def _reconcile_automatic_discount_counters(self, *, dry_run: bool) -> dict[str, int]:
        valid_orders = Order.objects.exclude(status=Order.OrderStatus.CANCELLED).exclude(
            financial_status=Order.FinancialStatus.VOIDED
        )
        expected = Counter(
            OrderDiscount.objects.filter(
                discount_type=OrderDiscount.DiscountType.AUTOMATIC,
                order__in=valid_orders,
            ).values_list("discount_id", flat=True)
        )
        updated = 0
        with transaction.atomic():
            for discount in AutomaticDiscount.objects.all():
                expected_count = int(expected.get(discount.id, 0))
                if int(discount.usage_count or 0) == expected_count:
                    continue
                updated += 1
                if not dry_run:
                    discount.usage_count = expected_count
                    discount.save(update_fields=["usage_count", "updated_at"])
        return {"updated": updated}

    def _reconcile_flash_sale_units(self, *, dry_run: bool) -> dict[str, int]:
        valid_items = OrderItem.objects.select_related("order").exclude(
            order__status=Order.OrderStatus.CANCELLED
        ).exclude(
            order__financial_status=Order.FinancialStatus.VOIDED
        )
        expected: Counter[str] = Counter()
        for item in valid_items:
            pricing_snapshot = (item.custom_properties or {}).get("pricing_snapshot", {})
            flash_sale_item_id = str(pricing_snapshot.get("flash_sale_item_id") or "").strip()
            if not flash_sale_item_id:
                continue
            expected[flash_sale_item_id] += int(item.quantity or 0)

        updated = 0
        with transaction.atomic():
            for flash_item in FlashSaleItem.objects.all():
                expected_count = int(expected.get(str(flash_item.id), 0))
                if int(flash_item.units_sold or 0) == expected_count:
                    continue
                updated += 1
                if not dry_run:
                    flash_item.units_sold = expected_count
                    flash_item.save(update_fields=["units_sold", "updated_at"])
        return {"updated": updated}
