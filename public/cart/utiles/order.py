"""
orders/utils/order.py
=====================
Order creation, status transitions, customer-facing lookups,
checkout validation, and reorder functionality.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("orders.order")


# ─────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────

class OrderError(Exception):
    pass


class CheckoutValidationError(OrderError):
    def __init__(self, message, field_errors=None):
        super().__init__(message)
        self.field_errors = field_errors or {}


# ─────────────────────────────────────────────────────────────
# RESULT TYPES
# ─────────────────────────────────────────────────────────────

@dataclass
class OrderTotals:
    subtotal_price: Decimal = Decimal("0.00")
    total_discounts: Decimal = Decimal("0.00")
    total_shipping: Decimal = Decimal("0.00")
    total_tax: Decimal = Decimal("0.00")
    total_price: Decimal = Decimal("0.00")
    currency: str = "USD"
    tax_lines: list = field(default_factory=list)
    discount_lines: list = field(default_factory=list)


@dataclass
class PlaceOrderResult:
    order: object = None
    success: bool = False
    errors: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — ORDER NUMBER GENERATION
# ─────────────────────────────────────────────────────────────

def generate_order_number(prefix: str = "ORD") -> tuple:
    """
    Generate a unique human-readable order number and its sequence integer.

    Strategy: Use a DB-level sequence via SELECT FOR UPDATE on the last
    order to prevent gaps or duplicates under concurrent load.

    Returns:
        tuple: (order_number: str, sequence: int)
        e.g. ("ORD-000123", 123)
    """
    from orders.models import Order

    with transaction.atomic():
        last_order = (
            Order.objects.select_for_update()
            .order_by("-order_number_sequence")
            .only("order_number_sequence")
            .first()
        )
        sequence = (last_order.order_number_sequence + 1) if last_order else 1
        order_number = f"{prefix}-{sequence:06d}"
        return order_number, sequence


# ─────────────────────────────────────────────────────────────
# SECTION 2 — CHECKOUT VALIDATION
# ─────────────────────────────────────────────────────────────

def validate_checkout_data(cart, shipping_address: dict, billing_address: dict = None) -> dict:
    """
    Validate all data required to convert a cart to an order.

    Checks:
      1. Cart has items
      2. All items still in stock
      3. All items still active/available
      4. Prices haven't changed beyond acceptable threshold
      5. Shipping address is complete
      6. Cart has a shipping rate selected
      7. Discount codes are still valid

    Args:
        cart: Cart instance with items prefetched
        shipping_address: Dict with required address fields
        billing_address: Optional; defaults to shipping_address if None

    Returns:
        dict: {
            "valid": bool,
            "errors": list[str],
            "field_errors": dict,
            "price_changed_items": list,
        }

    Raises:
        CheckoutValidationError: If critical errors exist.
    """
    errors = []
    field_errors = {}
    price_changed_items = []

    # ── 1. Cart has items ──
    items = list(cart.items.select_related("variant__product").all())
    if not items:
        raise CheckoutValidationError("Your cart is empty.")

    # ── 2 & 3. Item availability and stock ──
    for item in items:
        variant = item.variant

        if not variant.is_active or variant.product.status != "active":
            errors.append(
                f"'{item.product_title}' is no longer available and "
                f"has been removed from your cart."
            )
            item.delete()
            continue

        if variant.track_inventory and not variant.allow_backorder:
            if variant.available_quantity < item.quantity:
                if variant.available_quantity == 0:
                    errors.append(
                        f"'{item.product_title}' is out of stock."
                    )
                else:
                    errors.append(
                        f"Only {variant.available_quantity} unit(s) of "
                        f"'{item.product_title}' are available. "
                        f"Please update your quantity."
                    )

        # ── 4. Price drift check ──
        current_price = variant.effective_price
        if item.unit_price != current_price:
            price_changed_items.append({
                "sku": item.sku,
                "title": item.product_title,
                "old_price": item.unit_price,
                "new_price": current_price,
            })
            # Update cart item to current price
            item.unit_price = current_price
            item.save(update_fields=["unit_price", "updated_at"])

    # ── 5. Shipping address ──
    required_address_fields = ["first_name", "last_name", "address_line1", "city", "country"]
    for f in required_address_fields:
        if not shipping_address.get(f, "").strip():
            field_errors[f"shipping_{f}"] = f"This field is required."

    # ── 6. Shipping rate ──
    shippable_items = [i for i in items if i.requires_shipping]
    if shippable_items and not cart.shipping_rate_id:
        errors.append("Please select a shipping method.")
        field_errors["shipping_rate"] = "A shipping method is required."

    # ── 7. Discount code re-validation ──
    if cart.discount_code:
        discount_valid = _revalidate_discount_code(cart.discount_code, cart)
        if not discount_valid:
            errors.append(
                f"Discount code '{cart.discount_code}' is no longer valid "
                f"and has been removed."
            )
            from orders.models import CartDiscount
            cart.discounts.filter(
                discount_type=CartDiscount.DiscountType.CODE
            ).delete()
            cart.discount_code = ""
            cart.save(update_fields=["discount_code"])

    valid = len(errors) == 0 and len(field_errors) == 0

    return {
        "valid": valid,
        "errors": errors,
        "field_errors": field_errors,
        "price_changed_items": price_changed_items,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 3 — ORDER TOTALS CALCULATION
# ─────────────────────────────────────────────────────────────

def calculate_order_totals(cart) -> OrderTotals:
    """
    Calculate the final order totals from the cart state.
    Used to preview totals before order placement and to
    populate the Order record itself.

    Returns:
        OrderTotals: Full breakdown of all money fields.
    """
    TWO_PLACES = Decimal("0.01")
    items = list(cart.items.select_related("variant__product").all())
    discounts = list(cart.discounts.all())

    subtotal = sum(
        (i.unit_price * i.quantity for i in items),
        Decimal("0.00")
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    total_discounts = min(
        sum((d.amount for d in discounts), Decimal("0.00")),
        subtotal
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    total_shipping = cart.shipping_total or Decimal("0.00")
    total_tax = cart.tax_total or Decimal("0.00")

    total_price = (
        subtotal - total_discounts + total_shipping + total_tax
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    tax_lines = _build_tax_lines(cart, subtotal - total_discounts)
    discount_lines = [
        {
            "code": d.code,
            "type": d.discount_type,
            "description": d.description,
            "amount": d.amount,
        }
        for d in discounts
    ]

    return OrderTotals(
        subtotal_price=subtotal,
        total_discounts=total_discounts,
        total_shipping=total_shipping,
        total_tax=total_tax,
        total_price=max(total_price, Decimal("0.00")),
        currency=cart.currency,
        tax_lines=tax_lines,
        discount_lines=discount_lines,
    )


# ─────────────────────────────────────────────────────────────
# SECTION 4 — ORDER PLACEMENT
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def place_order_from_cart(
    cart,
    shipping_address: dict,
    billing_address: dict = None,
    customer_note: str = "",
    source: str = "web",
    actor=None,
) -> PlaceOrderResult:
    """
    Convert a validated Cart into a confirmed Order.
    This is the core checkout completion function.

    Steps:
      1. Validate cart state one final time (race condition guard)
      2. Calculate final totals
      3. Generate order number
      4. Create Order record
      5. Create OrderItem records (with full snapshots)
      6. Create OrderAddress records (shipping + billing)
      7. Create OrderDiscount records
      8. Create OrderTax records
      9. Reserve inventory for all items
      10. Mark cart as CONVERTED
      11. Write initial OrderStatusHistory entry
      12. Fire post-order signal (for notifications, webhooks, etc.)

    Args:
        cart: Active Cart with items.
        shipping_address: Dict of address fields.
        billing_address: If None, uses shipping_address.
        customer_note: Customer's order note from checkout.
        source: Order source string.
        actor: The User or None (for guest).

    Returns:
        PlaceOrderResult with the created Order.

    Raises:
        OrderError: For unrecoverable errors during placement.
    """
    from orders.models import (
        Order, OrderItem, OrderAddress, OrderDiscount,
        OrderTax, OrderStatusHistory,
    )
    from orders.utils.cart import recalculate_cart_totals

    # ── Final validation guard ──
    validation = validate_checkout_data(
        cart,
        shipping_address,
        billing_address or shipping_address,
    )
    if not validation["valid"]:
        return PlaceOrderResult(
            success=False,
            errors=validation["errors"] + list(validation["field_errors"].values()),
        )

    # ── Recalculate totals fresh ──
    recalculate_cart_totals(cart)
    totals = calculate_order_totals(cart)

    # ── Generate order number ──
    order_number, sequence = generate_order_number()

    # ── Customer info ──
    customer = cart.customer
    billing = billing_address or shipping_address

    customer_email = (
        customer.email if customer else cart.email
    )
    customer_name = (
        f"{shipping_address.get('first_name', '')} "
        f"{shipping_address.get('last_name', '')}".strip()
    )
    customer_phone = shipping_address.get("phone", "")

    # ── Create Order ──
    order = Order.objects.create(
        order_number=order_number,
        order_number_sequence=sequence,
        customer=customer,
        cart_id=cart.id,
        customer_email=customer_email,
        customer_phone=customer_phone,
        customer_name=customer_name,
        status=Order.OrderStatus.PENDING,
        financial_status=Order.FinancialStatus.PENDING,
        fulfillment_status=Order.FulfillmentStatus.UNFULFILLED,
        source=source,
        currency=cart.currency,
        subtotal_price=totals.subtotal_price,
        total_discounts=totals.total_discounts,
        total_shipping=totals.total_shipping,
        total_tax=totals.total_tax,
        total_price=totals.total_price,
        total_outstanding=totals.total_price,
        total_paid=Decimal("0.00"),
        total_refunded=Decimal("0.00"),
        shipping_rate_id=cart.shipping_rate_id,
        shipping_method_name=_get_shipping_method_name(cart.shipping_rate_id),
        taxes_included=False,
        customer_note=customer_note or cart.customer_note,
        ip_address=cart.ip_address,
        user_agent=cart.user_agent,
        utm_source=cart.utm_source,
        utm_medium=cart.utm_medium,
        utm_campaign=cart.utm_campaign,
        referrer_url=cart.referrer_url,
        buyer_accepts_marketing=getattr(customer, "accepts_marketing", False),
    )

    # ── Create OrderItems ──
    for cart_item in cart.items.select_related("variant__product").all():
        variant = cart_item.variant
        unit_discount = _calculate_line_discount(
            cart_item, totals.total_discounts, totals.subtotal_price
        )
        unit_tax_rate = _get_variant_tax_rate(variant, cart)
        unit_tax = (
            (cart_item.unit_price - unit_discount) * unit_tax_rate
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        line_subtotal = (
            cart_item.unit_price * cart_item.quantity
            - unit_discount * cart_item.quantity
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        line_total = (line_subtotal + unit_tax * cart_item.quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=cart_item.quantity,
            quantity_fulfilled=0,
            quantity_returned=0,
            quantity_refunded=0,
            # Immutable snapshots
            product_id_snapshot=variant.product.id,
            variant_id_snapshot=variant.id,
            product_title=cart_item.product_title,
            variant_title=cart_item.variant_title,
            sku=cart_item.sku,
            vendor=variant.product.vendor,
            product_image_url=cart_item.product_image_url,
            # Pricing
            unit_price=cart_item.unit_price,
            compare_at_price=cart_item.compare_at_price,
            unit_discount=unit_discount,
            unit_tax=unit_tax,
            tax_rate=unit_tax_rate,
            total_discount=unit_discount * cart_item.quantity,
            total_tax=unit_tax * cart_item.quantity,
            subtotal=line_subtotal,
            total=line_total,
            cost_per_item=variant.cost_per_item,
            # Tax
            tax_lines=_build_line_tax_lines(variant, unit_tax),
            is_taxable=variant.product.is_taxable,
            # Physical
            requires_shipping=cart_item.requires_shipping,
            weight=variant.weight,
            fulfillment_service=variant.fulfillment_service,
            custom_properties=cart_item.custom_properties,
            applied_discount_ids=[
                str(d.discount_id) for d in cart.discounts.all() if d.discount_id
            ],
        )

    # ── Create OrderAddresses ──
    _create_order_address(order, shipping_address, "shipping")
    _create_order_address(order, billing, "billing")

    # ── Create OrderDiscounts ──
    for cart_discount in cart.discounts.all():
        OrderDiscount.objects.create(
            order=order,
            discount_type=cart_discount.discount_type,
            code=cart_discount.code,
            description=cart_discount.description,
            discount_id=cart_discount.discount_id,
            amount=cart_discount.amount,
            is_percentage=cart_discount.is_percentage,
            percentage_value=cart_discount.percentage_value,
        )

    # ── Create OrderTax lines ──
    for tax_line in totals.tax_lines:
        OrderTax.objects.create(
            order=order,
            title=tax_line["title"],
            rate=tax_line["rate"],
            amount=tax_line["amount"],
            is_included_in_price=False,
            jurisdiction=tax_line.get("jurisdiction", ""),
        )

    # ── Reserve inventory ──
    _reserve_inventory_for_order(order)

    # ── Mark cart converted ──
    cart.mark_converted(order.id)

    # ── Initial history record ──
    OrderStatusHistory.objects.create(
        order=order,
        from_status="",
        to_status=Order.OrderStatus.PENDING,
        financial_status_snapshot=Order.FinancialStatus.PENDING,
        fulfillment_status_snapshot=Order.FulfillmentStatus.UNFULFILLED,
        source=OrderStatusHistory.ChangeSource.CUSTOMER,
        changed_by=actor,
        note="Order placed successfully.",
        is_customer_visible=True,
    )

    logger.info(
        "Order %s created (total=%s %s, customer=%s)",
        order.order_number,
        order.currency,
        order.total_price,
        customer_email,
    )

    return PlaceOrderResult(order=order, success=True)


# ─────────────────────────────────────────────────────────────
# SECTION 5 — ORDER TRANSITIONS
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def confirm_order(order, actor=None) -> None:
    """
    Transition order from PENDING → CONFIRMED after payment is authorized.
    Called by the payment webhook handler.
    """
    from orders.models import Order

    if order.status != Order.OrderStatus.PENDING:
        raise OrderError(
            f"Cannot confirm order in status '{order.status}'."
        )
    order.transition_status(
        Order.OrderStatus.CONFIRMED,
        actor=actor,
        note="Payment confirmed. Order is being prepared.",
        source="payment_gateway",
    )
    order.financial_status = Order.FinancialStatus.PAID
    order.total_paid = order.total_price
    order.total_outstanding = Decimal("0.00")
    order.confirmed_at = timezone.now()
    order.save(update_fields=[
        "financial_status", "total_paid", "total_outstanding", "confirmed_at", "updated_at"
    ])
    logger.info("Order %s confirmed (paid).", order.order_number)


@transaction.atomic
def cancel_order(order, reason: str, actor=None, note: str = "") -> None:
    """
    Cancel an order and release its inventory reservations.
    Only cancellable if status is PENDING, CONFIRMED, or ON_HOLD.
    """
    from orders.models import Order

    if not order.is_cancellable:
        raise OrderError(
            f"Order {order.order_number} cannot be cancelled "
            f"in its current status '{order.status}'."
        )

    # Release all inventory reservations
    _release_inventory_reservations(order)

    order.cancel(reason=reason, actor=actor, note=note)
    logger.info(
        "Order %s cancelled. Reason: %s", order.order_number, reason
    )


# ─────────────────────────────────────────────────────────────
# SECTION 6 — CUSTOMER-FACING LOOKUPS
# ─────────────────────────────────────────────────────────────

def get_order_for_customer(order_number: str, customer) -> object:
    """
    Fetch a single order belonging to a customer.
    Raises OrderError if not found or not owned by customer.

    Returns:
        Order with related data prefetched.
    """
    from orders.models import Order

    try:
        order = (
            Order.objects
            .prefetch_related(
                "items",
                "addresses",
                "fulfillments__fulfillment_items__order_item",
                "fulfillments__tracking_info",
                "returns__items",
                "refunds",
                "discounts",
                "tax_lines",
                "status_history",
                "notes",
            )
            .get(order_number=order_number, customer=customer)
        )
        return order
    except Order.DoesNotExist:
        raise OrderError(
            f"Order {order_number} not found."
        )


def get_orders_for_customer(
    customer,
    status: str = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """
    Paginated order list for the customer's account dashboard.

    Args:
        customer: accounts.Customer instance.
        status: Optional status filter.
        page: Page number (1-indexed).
        page_size: Items per page.

    Returns:
        dict: {
            "orders": QuerySet,
            "total": int,
            "page": int,
            "page_size": int,
            "total_pages": int,
            "has_next": bool,
            "has_previous": bool,
        }
    """
    from orders.models import Order
    import math

    qs = (
        Order.objects
        .filter(customer=customer)
        .prefetch_related(
            "items",
            "fulfillments__tracking_info",
        )
        .order_by("-placed_at")
    )

    if status:
        qs = qs.filter(status=status)

    total = qs.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size

    return {
        "orders": qs[offset : offset + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }


def get_order_timeline(order) -> list:
    """
    Build the customer-visible order timeline for the order tracking page.
    Combines status history, fulfillment events, and tracking scans.

    Returns:
        list[dict]: Sorted chronological list of timeline events.
        Each dict: {timestamp, event_type, title, description, icon, is_current}
    """
    events = []

    # ── Status history (customer-visible only) ──
    for history in order.status_history.filter(is_customer_visible=True).order_by("created_at"):
        events.append({
            "timestamp": history.created_at,
            "event_type": "status_change",
            "title": _status_to_label(history.to_status),
            "description": history.note,
            "icon": _status_to_icon(history.to_status),
            "is_current": False,
        })

    # ── Fulfillment tracking events ──
    for fulfillment in order.fulfillments.prefetch_related("tracking_info").all():
        for tracking in fulfillment.tracking_info.all():
            for event in tracking.tracking_events:
                events.append({
                    "timestamp": _parse_tracking_ts(event.get("timestamp")),
                    "event_type": "tracking",
                    "title": event.get("status", "Update"),
                    "description": f"{event.get('description', '')} — {event.get('location', '')}",
                    "icon": "truck",
                    "carrier": tracking.carrier_name,
                    "tracking_number": tracking.tracking_number,
                    "tracking_url": tracking.tracking_url,
                    "is_current": False,
                })

    # Sort by timestamp
    events.sort(key=lambda e: e["timestamp"] or timezone.now())

    # Mark the last event as current
    if events:
        events[-1]["is_current"] = True

    return events


def reorder(original_order, customer) -> dict:
    """
    Re-add all available items from a past order into a new cart.
    Skips discontinued or out-of-stock items with explanation.

    Returns:
        dict: {
            "cart": Cart,
            "added": list,
            "skipped": list[{title, reason}],
        }
    """
    from orders.utils.cart import get_or_create_cart, add_item_to_cart, CartItemError

    added = []
    skipped = []

    # Create a dummy request-like object is not available here;
    # caller should pass a real request. We use a lightweight wrapper.
    class FakeRequest:
        session = type("S", (), {"session_key": "reorder", "create": lambda: None})()
        META = {}
        COOKIES = {}
        headers = {}
        user = customer.user if hasattr(customer, "user") else None

    cart = get_or_create_cart(FakeRequest(), currency=original_order.currency)
    cart.customer = customer
    cart.save(update_fields=["customer"])

    for item in original_order.items.select_related("variant__product").all():
        if item.variant is None:
            skipped.append({
                "title": item.product_title,
                "reason": "Product no longer available.",
            })
            continue

        try:
            add_item_to_cart(cart, item.variant, quantity=item.quantity)
            added.append({"title": item.product_title, "sku": item.sku})
        except CartItemError as e:
            skipped.append({"title": item.product_title, "reason": str(e)})

    return {"cart": cart, "added": added, "skipped": skipped}


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _reserve_inventory_for_order(order) -> None:
    """Reserve inventory for every line item in a newly placed order."""
    from inventory.models import InventoryLevel

    for item in order.items.select_related("variant").all():
        variant = item.variant
        if not variant or not variant.track_inventory:
            continue

        level = InventoryLevel.objects.filter(
            variant=variant,
            location__is_default=True,
            is_active=True,
        ).select_for_update().first()

        if level:
            try:
                level.reserve(
                    quantity=item.quantity,
                    reference=order.order_number,
                )
            except ValueError as e:
                logger.warning(
                    "Could not reserve stock for %s on order %s: %s",
                    variant.sku, order.order_number, e
                )


def _release_inventory_reservations(order) -> None:
    """Release all inventory reservations held by a cancelled order."""
    from inventory.models import InventoryLevel

    for item in order.items.select_related("variant").all():
        variant = item.variant
        if not variant or not variant.track_inventory:
            continue

        level = InventoryLevel.objects.filter(
            variant=variant,
            location__is_default=True,
            is_active=True,
        ).select_for_update().first()

        if level:
            level.release_reservation(
                quantity=item.quantity,
                reference=order.order_number,
            )


def _create_order_address(order, address_dict: dict, address_type: str) -> None:
    from orders.models import OrderAddress

    OrderAddress.objects.create(
        order=order,
        address_type=address_type,
        first_name=address_dict.get("first_name", ""),
        last_name=address_dict.get("last_name", ""),
        company=address_dict.get("company", ""),
        address_line1=address_dict.get("address_line1", ""),
        address_line2=address_dict.get("address_line2", ""),
        city=address_dict.get("city", ""),
        state=address_dict.get("state", ""),
        postal_code=address_dict.get("postal_code", ""),
        country=address_dict.get("country", ""),
        country_name=address_dict.get("country_name", ""),
        phone=address_dict.get("phone", ""),
        email=address_dict.get("email", ""),
    )


def _calculate_line_discount(cart_item, total_discounts, total_subtotal) -> Decimal:
    """
    Prorate order-level discounts across each line item proportionally.
    Returns per-unit discount for this line.
    """
    if total_subtotal == 0 or total_discounts == 0:
        return Decimal("0.00")
    line_total = cart_item.unit_price * cart_item.quantity
    proportion = line_total / total_subtotal
    line_discount = (total_discounts * proportion) / cart_item.quantity
    return line_discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _get_variant_tax_rate(variant, cart) -> Decimal:
    """Get applicable tax rate for a variant based on product tax class."""
    return Decimal("0.0000")  # Override with real tax engine lookup


def _build_tax_lines(cart, taxable_amount: Decimal) -> list:
    """Build tax line descriptors for the order."""
    if not taxable_amount or taxable_amount <= 0:
        return []
    return [
        {
            "title": "Tax",
            "rate": Decimal("0.00"),
            "amount": cart.tax_total or Decimal("0.00"),
            "jurisdiction": "",
        }
    ]


def _build_line_tax_lines(variant, unit_tax: Decimal) -> list:
    if unit_tax <= 0:
        return []
    return [{"title": "Tax", "rate": "0.00", "amount": str(unit_tax)}]


def _get_shipping_method_name(shipping_rate_id) -> str:
    if not shipping_rate_id:
        return ""
    try:
        from shipping.models import ShippingRate
        rate = ShippingRate.objects.filter(id=shipping_rate_id).values("name").first()
        return rate["name"] if rate else ""
    except Exception:
        return ""


def _revalidate_discount_code(code: str, cart) -> bool:
    """Quick re-check if a discount code is still usable at checkout."""
    try:
        from pricing.models import DiscountCode
        discount = DiscountCode.objects.get(code__iexact=code.strip(), is_active=True)
        now = timezone.now()
        if discount.starts_at and discount.starts_at > now:
            return False
        if discount.ends_at and discount.ends_at < now:
            return False
        if discount.usage_limit and discount.usage_count >= discount.usage_limit:
            return False
        return True
    except Exception:
        return False


def _status_to_label(status: str) -> str:
    labels = {
        "pending": "Order Placed",
        "confirmed": "Order Confirmed",
        "processing": "Being Prepared",
        "shipped": "Shipped",
        "delivered": "Delivered",
        "cancelled": "Cancelled",
        "completed": "Completed",
    }
    return labels.get(status, status.replace("_", " ").title())


def _status_to_icon(status: str) -> str:
    icons = {
        "pending": "clock",
        "confirmed": "check-circle",
        "processing": "package",
        "shipped": "truck",
        "delivered": "check-badge",
        "cancelled": "x-circle",
    }
    return icons.get(status, "circle")


def _parse_tracking_ts(ts_str):
    if not ts_str:
        return timezone.now()
    try:
        from dateutil import parser as dateparser
        return dateparser.parse(ts_str)
    except Exception:
        return timezone.now()
