"""
orders/utils/fulfillment.py
===========================
Fulfillment creation, shipment tracking, status management,
and the unfulfilled order queue for the staff dashboard.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("orders.fulfillment")


class FulfillmentError(Exception):
    pass


@dataclass
class FulfillmentResult:
    fulfillment: object = None
    success: bool = False
    message: str = ""
    stock_warnings: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — CREATE FULFILLMENT
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def create_fulfillment(
    order,
    line_items: List[dict],
    location=None,
    carrier=None,
    tracking_number: str = "",
    tracking_url: str = "",
    carrier_name: str = "",
    shipping_method: str = "",
    notify_customer: bool = True,
    packing_instructions: str = "",
    actor=None,
) -> FulfillmentResult:
    """
    Create a Fulfillment (shipment) for one or more order line items.

    Args:
        order: Order instance.
        line_items: [{"order_item_id": uuid, "quantity": int}, ...]
        location: inventory.InventoryLocation to fulfill from.
        carrier: shipping.ShippingCarrier instance (optional).
        tracking_number: Carrier tracking number.
        tracking_url: Carrier tracking page URL.
        carrier_name: Carrier display name.
        shipping_method: Human-readable method name.
        notify_customer: Send shipment email.
        packing_instructions: Internal instructions for packers.
        actor: Staff user performing this action.

    Returns:
        FulfillmentResult with the created Fulfillment.

    Raises:
        FulfillmentError: For validation failures.
    """
    from orders.models import (
        Order, OrderItem, Fulfillment, FulfillmentItem,
        TrackingInfo, OrderStatusHistory,
    )

    if not line_items:
        raise FulfillmentError("At least one line item is required to create a fulfillment.")

    stock_warnings = []

    # ── Validate and lock order items ──
    order_item_ids = [li["order_item_id"] for li in line_items]
    order_items = {
        str(oi.id): oi
        for oi in OrderItem.objects.filter(
            id__in=order_item_ids,
            order=order,
        ).select_for_update()
    }

    for li in line_items:
        item_id = str(li["order_item_id"])
        qty = li["quantity"]

        if item_id not in order_items:
            raise FulfillmentError(f"Order item {item_id} not found on this order.")

        oi = order_items[item_id]
        unfulfilled = oi.quantity_unfulfilled
        if qty > unfulfilled:
            raise FulfillmentError(
                f"Cannot fulfill {qty} units of '{oi.product_title}'. "
                f"Only {unfulfilled} unfulfilled unit(s) remain."
            )

    # ── Build fulfillment number ──
    existing_count = order.fulfillments.count()
    fulfillment_number = build_fulfillment_number(order.order_number, existing_count + 1)

    # ── Destination snapshot ──
    shipping_addr = order.addresses.filter(address_type="shipping").first()
    destination_name = shipping_addr.full_name if shipping_addr else ""
    destination_address = shipping_addr.full_address if shipping_addr else ""
    destination_city = shipping_addr.city if shipping_addr else ""
    destination_country = shipping_addr.country if shipping_addr else ""

    # ── Create Fulfillment ──
    fulfillment = Fulfillment.objects.create(
        order=order,
        fulfillment_number=fulfillment_number,
        status=Fulfillment.FulfillmentStatus.PENDING,
        location=location,
        carrier=carrier,
        shipping_method=shipping_method,
        destination_name=destination_name,
        destination_address=destination_address,
        destination_city=destination_city,
        destination_country=destination_country,
        notify_customer=notify_customer,
        packing_instructions=packing_instructions,
        created_by=actor,
    )

    # ── Create FulfillmentItems and update OrderItem quantities ──
    for li in line_items:
        item_id = str(li["order_item_id"])
        qty = li["quantity"]
        oi = order_items[item_id]

        FulfillmentItem.objects.create(
            fulfillment=fulfillment,
            order_item=oi,
            quantity=qty,
        )

        oi.quantity_fulfilled += qty
        oi.save(update_fields=["quantity_fulfilled", "updated_at"])

        # ── Deduct stock from inventory ──
        warning = _deduct_stock_for_fulfillment(oi.variant, qty, location, order)
        if warning:
            stock_warnings.append(warning)

    # ── Attach tracking info ──
    if tracking_number:
        TrackingInfo.objects.create(
            fulfillment=fulfillment,
            carrier_name=carrier_name or (carrier.name if carrier else ""),
            carrier_code=carrier.code if carrier else "",
            tracking_number=tracking_number,
            tracking_url=tracking_url,
            status=TrackingInfo.TrackingStatus.LABEL_CREATED,
            is_primary=True,
            shipped_at=timezone.now(),
        )
        fulfillment.shipped_at = timezone.now()
        fulfillment.status = Fulfillment.FulfillmentStatus.SHIPPED
        fulfillment.save(update_fields=["status", "shipped_at", "updated_at"])

    # ── Update order fulfillment status ──
    _update_order_fulfillment_status(order)

    # ── Write history ──
    OrderStatusHistory.objects.create(
        order=order,
        from_status=order.status,
        to_status=order.status,
        financial_status_snapshot=order.financial_status,
        fulfillment_status_snapshot=order.fulfillment_status,
        source=OrderStatusHistory.ChangeSource.STAFF,
        changed_by=actor,
        note=(
            f"Fulfillment {fulfillment_number} created. "
            + (f"Tracking: {tracking_number}" if tracking_number else "")
        ),
        is_customer_visible=bool(tracking_number),
    )

    logger.info(
        "Fulfillment %s created for order %s (%d item lines)",
        fulfillment_number, order.order_number, len(line_items)
    )

    return FulfillmentResult(
        fulfillment=fulfillment,
        success=True,
        message=f"Fulfillment {fulfillment_number} created successfully.",
        stock_warnings=stock_warnings,
    )


# ─────────────────────────────────────────────────────────────
# SECTION 2 — STATUS UPDATES
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def mark_fulfillment_shipped(
    fulfillment,
    tracking_number: str,
    tracking_url: str = "",
    carrier_name: str = "",
    carrier_code: str = "",
    actor=None,
) -> None:
    """
    Mark a fulfillment as shipped and attach/update tracking info.
    Updates order fulfillment_status accordingly.
    """
    from orders.models import TrackingInfo, OrderStatusHistory

    if fulfillment.status in (
        Fulfillment.FulfillmentStatus.DELIVERED,
        Fulfillment.FulfillmentStatus.CANCELLED,
    ):
        raise FulfillmentError(
            f"Cannot mark fulfillment as shipped — current status: {fulfillment.status}"
        )

    # Upsert tracking info
    tracking, _ = TrackingInfo.objects.update_or_create(
        fulfillment=fulfillment,
        is_primary=True,
        defaults={
            "tracking_number": tracking_number,
            "tracking_url": tracking_url,
            "carrier_name": carrier_name,
            "carrier_code": carrier_code,
            "status": TrackingInfo.TrackingStatus.IN_TRANSIT,
            "shipped_at": timezone.now(),
        },
    )

    from orders.models import Fulfillment as F
    fulfillment.status = F.FulfillmentStatus.SHIPPED
    fulfillment.shipped_at = timezone.now()
    fulfillment.save(update_fields=["status", "shipped_at", "updated_at"])

    _update_order_fulfillment_status(fulfillment.order)

    OrderStatusHistory.objects.create(
        order=fulfillment.order,
        from_status=fulfillment.order.status,
        to_status=fulfillment.order.status,
        financial_status_snapshot=fulfillment.order.financial_status,
        fulfillment_status_snapshot=fulfillment.order.fulfillment_status,
        source=OrderStatusHistory.ChangeSource.STAFF,
        changed_by=actor,
        note=f"Shipped via {carrier_name}. Tracking: {tracking_number}",
        is_customer_visible=True,
    )


@transaction.atomic
def mark_fulfillment_delivered(fulfillment, actor=None) -> None:
    """Mark a fulfillment as delivered and update parent order status."""
    from orders.models import TrackingInfo, OrderStatusHistory, Fulfillment as F

    fulfillment.status = F.FulfillmentStatus.DELIVERED
    fulfillment.delivered_at = timezone.now()
    fulfillment.save(update_fields=["status", "delivered_at", "updated_at"])

    fulfillment.tracking_info.filter(is_primary=True).update(
        status=TrackingInfo.TrackingStatus.DELIVERED,
        delivered_at=timezone.now(),
    )

    _update_order_fulfillment_status(fulfillment.order)

    OrderStatusHistory.objects.create(
        order=fulfillment.order,
        from_status=fulfillment.order.status,
        to_status=fulfillment.order.status,
        source=OrderStatusHistory.ChangeSource.SHIPPING_CARRIER,
        note=f"Fulfillment {fulfillment.fulfillment_number} delivered.",
        is_customer_visible=True,
    )


@transaction.atomic
def cancel_fulfillment(fulfillment, actor=None, note: str = "") -> None:
    """
    Cancel a fulfillment and restore inventory reservations.
    Only allowed if not yet shipped.
    """
    from orders.models import Fulfillment as F, OrderStatusHistory

    if fulfillment.status in (
        F.FulfillmentStatus.SHIPPED,
        F.FulfillmentStatus.IN_TRANSIT,
        F.FulfillmentStatus.DELIVERED,
    ):
        raise FulfillmentError("Cannot cancel a fulfillment that has already shipped.")

    # Reverse quantity_fulfilled on order items
    for fi in fulfillment.fulfillment_items.select_related("order_item").all():
        oi = fi.order_item
        oi.quantity_fulfilled = max(0, oi.quantity_fulfilled - fi.quantity)
        oi.save(update_fields=["quantity_fulfilled", "updated_at"])

    fulfillment.status = F.FulfillmentStatus.CANCELLED
    fulfillment.save(update_fields=["status", "updated_at"])

    _update_order_fulfillment_status(fulfillment.order)

    OrderStatusHistory.objects.create(
        order=fulfillment.order,
        from_status=fulfillment.order.status,
        to_status=fulfillment.order.status,
        source=OrderStatusHistory.ChangeSource.STAFF,
        changed_by=actor,
        note=f"Fulfillment {fulfillment.fulfillment_number} cancelled. {note}",
        is_customer_visible=False,
    )
    logger.info("Fulfillment %s cancelled.", fulfillment.fulfillment_number)


# ─────────────────────────────────────────────────────────────
# SECTION 3 — TRACKING SYNC
# ─────────────────────────────────────────────────────────────

def sync_tracking_status(tracking_info) -> dict:
    """
    Fetch the latest carrier tracking status for a TrackingInfo record
    and update the database. Called by a periodic Celery task.

    Returns:
        dict: {"updated": bool, "new_status": str, "events_added": int}
    """
    from orders.models import TrackingInfo

    if not tracking_info.tracking_number:
        return {"updated": False, "new_status": tracking_info.status, "events_added": 0}

    result = _fetch_carrier_tracking(
        carrier_code=tracking_info.carrier_code,
        tracking_number=tracking_info.tracking_number,
    )

    if not result:
        return {"updated": False, "new_status": tracking_info.status, "events_added": 0}

    old_status = tracking_info.status
    new_events = result.get("events", [])
    new_status = result.get("status", tracking_info.status)

    existing_timestamps = {
        e.get("timestamp") for e in tracking_info.tracking_events
    }
    added = [e for e in new_events if e.get("timestamp") not in existing_timestamps]

    update_fields = ["last_synced_at", "updated_at"]

    if added:
        tracking_info.tracking_events = tracking_info.tracking_events + added
        update_fields.append("tracking_events")

    if new_status != old_status:
        tracking_info.status = new_status
        update_fields.append("status")

    if result.get("estimated_delivery"):
        tracking_info.estimated_delivery_at = result["estimated_delivery"]
        update_fields.append("estimated_delivery_at")

    if result.get("current_location"):
        tracking_info.current_location = result["current_location"]
        update_fields.append("current_location")

    if new_status == TrackingInfo.TrackingStatus.DELIVERED and not tracking_info.delivered_at:
        tracking_info.delivered_at = timezone.now()
        update_fields.append("delivered_at")
        mark_fulfillment_delivered(tracking_info.fulfillment)

    tracking_info.last_synced_at = timezone.now()
    tracking_info.save(update_fields=list(set(update_fields)))

    return {
        "updated": bool(added) or new_status != old_status,
        "new_status": new_status,
        "events_added": len(added),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 4 — DASHBOARD QUEUE HELPERS
# ─────────────────────────────────────────────────────────────

def get_unfulfilled_orders(
    location=None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """
    Return paginated queryset of orders that have unfulfilled items.
    Used to build the fulfillment queue on the staff dashboard.

    Args:
        location: Filter to orders assigned to a specific location.
        page: Page number.
        page_size: Results per page.

    Returns:
        dict with orders queryset and pagination metadata.
    """
    from orders.models import Order
    import math

    qs = (
        Order.objects
        .filter(
            status__in=[Order.OrderStatus.CONFIRMED, Order.OrderStatus.PROCESSING],
            fulfillment_status__in=[
                Order.FulfillmentStatus.UNFULFILLED,
                Order.FulfillmentStatus.PARTIALLY_FULFILLED,
            ],
        )
        .prefetch_related("items__variant", "addresses")
        .order_by("placed_at")  # oldest first for FIFO
    )

    if location:
        qs = qs.filter(items__variant__inventory_levels__location=location).distinct()

    total = qs.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size

    return {
        "orders": qs[offset : offset + page_size],
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
    }


def get_fulfillment_summary(order) -> dict:
    """
    Build a per-line fulfillment progress summary for a single order.
    Used on the order detail page in the staff dashboard.

    Returns:
        dict: {
            "total_items": int,
            "fulfilled_items": int,
            "unfulfilled_items": int,
            "fulfillment_percentage": float,
            "lines": [{"title", "sku", "ordered", "fulfilled", "remaining"}]
        }
    """
    items = order.items.select_related("variant").all()

    lines = []
    total_ordered = 0
    total_fulfilled = 0

    for item in items:
        lines.append({
            "order_item_id": str(item.id),
            "title": item.product_title,
            "variant_title": item.variant_title,
            "sku": item.sku,
            "ordered": item.quantity,
            "fulfilled": item.quantity_fulfilled,
            "returned": item.quantity_returned,
            "remaining": item.quantity_unfulfilled,
            "is_fully_fulfilled": item.is_fully_fulfilled,
        })
        total_ordered += item.quantity
        total_fulfilled += item.quantity_fulfilled

    pct = (total_fulfilled / total_ordered * 100) if total_ordered > 0 else 0

    return {
        "total_items": total_ordered,
        "fulfilled_items": total_fulfilled,
        "unfulfilled_items": total_ordered - total_fulfilled,
        "fulfillment_percentage": round(pct, 1),
        "is_fully_fulfilled": total_fulfilled >= total_ordered,
        "lines": lines,
    }


def build_fulfillment_number(order_number: str, index: int) -> str:
    """Generate a fulfillment number. e.g. ORD-000123-F1"""
    return f"{order_number}-F{index}"


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _deduct_stock_for_fulfillment(variant, quantity, location, order) -> Optional[str]:
    """
    Deduct fulfilled stock from inventory and convert reservation to actual sale.
    Returns a warning string if stock deduction had issues, else None.
    """
    if not variant or not variant.track_inventory:
        return None

    try:
        from inventory.models import InventoryLevel, StockMovement

        level = InventoryLevel.objects.filter(
            variant=variant,
            location=location or None,
            is_active=True,
        ).select_for_update().first()

        if not level:
            return f"No inventory level found for {variant.sku}."

        # Convert reservation → actual sale
        level.release_reservation(quantity)
        level.adjust(
            delta=-quantity,
            movement_type=StockMovement.MovementType.SALE,
            reference=order.order_number,
            note=f"Fulfilled in order {order.order_number}",
        )
        return None
    except Exception as e:
        logger.error("Stock deduction failed for %s: %s", variant.sku, e)
        return f"Stock deduction warning for {variant.sku}: {e}"


def _update_order_fulfillment_status(order) -> None:
    """
    Recompute and save the order's fulfillment_status based on
    the aggregate state of all its fulfillment records.
    """
    from orders.models import Order

    items = list(order.items.all())
    if not items:
        return

    total_qty = sum(i.quantity for i in items)
    fulfilled_qty = sum(i.quantity_fulfilled for i in items)
    returned_qty = sum(i.quantity_returned for i in items)

    active_fulfillments = order.fulfillments.exclude(
        status=order.fulfillments.model.FulfillmentStatus.CANCELLED
    )
    delivered_count = active_fulfillments.filter(
        status=order.fulfillments.model.FulfillmentStatus.DELIVERED
    ).count()
    total_active = active_fulfillments.count()

    if fulfilled_qty == 0:
        new_status = Order.FulfillmentStatus.UNFULFILLED
    elif returned_qty >= total_qty:
        new_status = Order.FulfillmentStatus.RETURNED
    elif returned_qty > 0:
        new_status = Order.FulfillmentStatus.PARTIALLY_RETURNED
    elif delivered_count == total_active and total_active > 0:
        new_status = Order.FulfillmentStatus.DELIVERED
    elif fulfilled_qty >= total_qty:
        new_status = Order.FulfillmentStatus.FULFILLED
    else:
        new_status = Order.FulfillmentStatus.PARTIALLY_FULFILLED

    if order.fulfillment_status != new_status:
        order.fulfillment_status = new_status
        order.save(update_fields=["fulfillment_status", "updated_at"])


def _fetch_carrier_tracking(carrier_code: str, tracking_number: str) -> Optional[dict]:
    """
    Stub for carrier API integration.
    Replace with real carrier SDK calls (Shippo, EasyPost, etc.).
    """
    logger.debug(
        "Fetching tracking for %s from carrier %s",
        tracking_number, carrier_code
    )
    return None
