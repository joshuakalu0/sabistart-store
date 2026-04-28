"""
orders/utils/returns.py
=======================
RMA creation, inspection workflow, disposition, and refund processing.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("orders.returns")


class ReturnError(Exception):
    pass


class RefundError(Exception):
    pass


@dataclass
class ReturnResult:
    return_request: object = None
    success: bool = False
    message: str = ""


@dataclass
class RefundResult:
    refund: object = None
    success: bool = False
    message: str = ""
    gateway_response: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — RETURN REQUEST
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def create_return_request(
    order,
    items: List[dict],
    reason: str,
    reason_note: str = "",
    return_method: str = "mail",
    customer=None,
) -> ReturnResult:
    """
    Create a Return Request (RMA) for one or more fulfilled order items.

    Args:
        order: Order instance.
        items: [{"order_item_id": uuid, "quantity": int, "reason": str}, ...]
        reason: Primary return reason (Return.ReturnReason choice).
        reason_note: Customer's freeform explanation.
        return_method: How items will come back (mail/drop_off/pickup).
        customer: accounts.Customer requesting the return.

    Returns:
        ReturnResult with the created Return.

    Raises:
        ReturnError: If items are not returnable.
    """
    from orders.models import Order, OrderItem, Return, ReturnItem

    # ── Validate order is in a returnable state ──
    if order.status not in (
        Order.OrderStatus.COMPLETED,
        Order.OrderStatus.PARTIALLY_RETURNED,
    ):
        raise ReturnError(
            f"Order {order.order_number} is not eligible for returns "
            f"(current status: {order.status})."
        )

    if not order.is_paid:
        raise ReturnError("Cannot process return for an unpaid order.")

    if not items:
        raise ReturnError(
            "At least one item is required for a return request.")

    # ── Validate each item ──
    returnable = get_returnable_items(order)
    returnable_map = {str(ri["order_item_id"]): ri for ri in returnable}

    for item_req in items:
        item_id = str(item_req["order_item_id"])
        qty = item_req.get("quantity", 1)

        if item_id not in returnable_map:
            raise ReturnError(
                f"Item {item_id} is not eligible for return."
            )
        if qty > returnable_map[item_id]["returnable_quantity"]:
            raise ReturnError(
                f"Cannot return {qty} units of "
                f"'{returnable_map[item_id]['product_title']}'. "
                f"Only {returnable_map[item_id]['returnable_quantity']} returnable."
            )

    # ── Generate return number ──
    return_number = _generate_return_number()

    # ── Create Return header ──
    return_obj = Return.objects.create(
        order=order,
        customer=customer or order.customer,
        return_number=return_number,
        status=Return.ReturnStatus.REQUESTED,
        reason=reason,
        reason_note=reason_note,
        return_method=return_method,
        requested_at=timezone.now(),
    )

    # ── Create ReturnItems ──
    for item_req in items:
        item_id = str(item_req["order_item_id"])
        qty = item_req.get("quantity", 1)
        oi = OrderItem.objects.get(id=item_id, order=order)

        ReturnItem.objects.create(
            return_request=return_obj,
            order_item=oi,
            quantity=qty,
            reason=item_req.get("reason", reason),
        )

    # ── Update order status ──
    order.status = Order.OrderStatus.PARTIALLY_RETURNED
    order.save(update_fields=["status", "updated_at"])

    # ── Log event ──
    from orders.models import ReturnEvent
    ReturnEvent.objects.create(
        return_request=return_obj,
        from_status="",
        to_status=Return.ReturnStatus.REQUESTED,
        event_note=f"Return requested by customer. Reason: {reason}",
        is_customer_visible=True,
    )

    logger.info(
        "Return %s created for order %s (%d items)",
        return_number, order.order_number, len(items)
    )

    return ReturnResult(
        return_request=return_obj,
        success=True,
        message=f"Return request {return_number} submitted successfully.",
    )


def get_returnable_items(order) -> List[dict]:
    """
    Determine which items and quantities are eligible for return.

    Eligibility criteria:
      - Item has been fulfilled (quantity_fulfilled > 0)
      - Not already returned (quantity_returned < quantity_fulfilled)

    Returns:
        list[dict]: [
            {
                "order_item_id", "product_title", "sku",
                "fulfilled_quantity", "returned_quantity",
                "returnable_quantity"
            }
        ]
    """
    returnable = []

    for item in order.items.select_related("variant").all():
        returnable_qty = item.quantity_fulfilled - item.quantity_returned
        if returnable_qty > 0:
            returnable.append({
                "order_item_id": item.id,
                "product_title": item.product_title,
                "variant_title": item.variant_title,
                "sku": item.sku,
                "fulfilled_quantity": item.quantity_fulfilled,
                "returned_quantity": item.quantity_returned,
                "returnable_quantity": returnable_qty,
                "unit_price": item.unit_price,
                "image_url": item.product_image_url,
            })

    return returnable


# ─────────────────────────────────────────────────────────────
# SECTION 2 — RETURN WORKFLOW
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def approve_return(return_request, actor, approved_amount: Decimal = None) -> None:
    """
    Approve a return request and optionally set the refund amount.
    Generates a return label if method is 'mail'.
    """
    from orders.models import ReturnEvent

    return_request.approve(actor=actor, approved_amount=approved_amount)

    ReturnEvent.objects.create(
        return_request=return_request,
        from_status=Return.ReturnStatus.PENDING_REVIEW,
        to_status=Return.ReturnStatus.APPROVED,
        event_note=f"Return approved by staff. Refund amount: {approved_amount}",
        performed_by=actor,
        is_customer_visible=True,
    )

    logger.info(
        "Return %s approved by %s", return_request.return_number, actor
    )


@transaction.atomic
def reject_return(return_request, actor, reason: str) -> None:
    """Reject a return request with a reason."""
    from orders.models import ReturnEvent

    return_request.reject(actor=actor, reason=reason)

    ReturnEvent.objects.create(
        return_request=return_request,
        from_status=Return.ReturnStatus.PENDING_REVIEW,
        to_status=Return.ReturnStatus.REJECTED,
        event_note=f"Return rejected: {reason}",
        performed_by=actor,
        is_customer_visible=True,
    )


@transaction.atomic
def receive_return_items(
    return_request,
    received_items: List[dict],
    actor=None,
) -> None:
    """
    Record that physical return items have been received at the warehouse.
    Updates quantity_received on each ReturnItem.

    Args:
        return_request: Return instance.
        received_items: [{"return_item_id": uuid, "quantity_received": int}]
        actor: Staff user receiving items.
    """
    from orders.models import ReturnEvent

    for ri_data in received_items:
        item = return_request.items.get(id=ri_data["return_item_id"])
        item.quantity_received = ri_data["quantity_received"]
        item.save(update_fields=["quantity_received", "updated_at"])

    return_request.status = Return.ReturnStatus.RECEIVED
    return_request.received_at = timezone.now()
    return_request.save(update_fields=["status", "received_at", "updated_at"])

    ReturnEvent.objects.create(
        return_request=return_request,
        from_status=Return.ReturnStatus.APPROVED,
        to_status=Return.ReturnStatus.RECEIVED,
        event_note="Items received at warehouse.",
        performed_by=actor,
        is_customer_visible=True,
    )


@transaction.atomic
def inspect_return_items(
    return_request,
    inspections: List[dict],
    actor=None,
) -> None:
    """
    Record inspection results for received return items.
    Sets condition and disposition on each ReturnItem.

    Args:
        return_request: Return instance.
        inspections: [
            {
                "return_item_id": uuid,
                "condition": ReturnItem.ItemCondition,
                "disposition": ReturnItem.ItemDisposition,
                "refund_amount": Decimal,
                "disposition_note": str,
            }
        ]
        actor: Staff user inspecting.
    """
    from orders.models import ReturnEvent

    for insp in inspections:
        item = return_request.items.get(id=insp["return_item_id"])
        item.condition = insp.get("condition", "")
        item.disposition = insp.get("disposition", "")
        item.refund_amount = insp.get("refund_amount")
        item.disposition_note = insp.get("disposition_note", "")
        item.save(update_fields=[
            "condition", "disposition", "refund_amount",
            "disposition_note", "updated_at"
        ])

    return_request.status = Return.ReturnStatus.INSPECTING
    return_request.save(update_fields=["status", "updated_at"])

    ReturnEvent.objects.create(
        return_request=return_request,
        from_status=Return.ReturnStatus.RECEIVED,
        to_status=Return.ReturnStatus.INSPECTING,
        event_note="Items inspected. Disposition decisions recorded.",
        performed_by=actor,
        is_customer_visible=False,
    )


@transaction.atomic
def complete_return_restock(return_request, location=None, actor=None) -> None:
    """
    Execute inventory restocking for items marked as RESTOCK or RESTOCK_AS_USED.
    Should be called after inspection is complete.
    """
    from orders.models import ReturnItem, ReturnEvent
    from inventory.models import StockMovement

    restocked_count = 0

    for item in return_request.items.select_related("order_item__variant").all():
        if item.disposition not in (
            ReturnItem.ItemDisposition.RESTOCK,
            ReturnItem.ItemDisposition.RESTOCK_AS_USED,
        ):
            continue

        variant = item.order_item.variant
        if not variant or not variant.track_inventory:
            continue

        restock_qty = item.quantity_received or item.quantity

        try:
            from inventory.models import InventoryLevel
            level = InventoryLevel.objects.filter(
                variant=variant,
                location=location,
                is_active=True,
            ).first()

            if level:
                level.adjust(
                    delta=restock_qty,
                    movement_type=StockMovement.MovementType.REFUND_RESTOCK,
                    reference=return_request.return_number,
                    note=f"Restocked from return {return_request.return_number}",
                    actor=actor,
                )
                item.quantity_restocked = restock_qty
                item.save(update_fields=["quantity_restocked", "updated_at"])
                restocked_count += restock_qty
        except Exception as e:
            logger.error(
                "Restock failed for %s on return %s: %s",
                variant.sku, return_request.return_number, e
            )

    return_request.status = Return.ReturnStatus.RESTOCKED
    return_request.save(update_fields=["status", "updated_at"])

    ReturnEvent.objects.create(
        return_request=return_request,
        from_status=Return.ReturnStatus.INSPECTING,
        to_status=Return.ReturnStatus.RESTOCKED,
        event_note=f"{restocked_count} units restocked to inventory.",
        performed_by=actor,
        is_customer_visible=False,
    )


# ─────────────────────────────────────────────────────────────
# SECTION 3 — REFUNDS
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def create_refund_from_return(
    return_request,
    method: str = "original_payment",
    actor=None,
    notify_customer: bool = True,
) -> RefundResult:
    """
    Create a Refund from an approved and inspected Return.
    Uses the approved_amount set on the Return.

    Returns:
        RefundResult with the created Refund.
    """
    from orders.models import Refund, RefundLineItem, ReturnEvent

    if not return_request.refund_amount:
        raise RefundError(
            f"Return {return_request.return_number} has no approved refund amount set."
        )

    net_amount = return_request.net_refund_amount
    if net_amount is None or net_amount <= 0:
        raise RefundError("Net refund amount must be greater than zero.")

    refund_number = _generate_refund_number()

    refund = Refund.objects.create(
        order=return_request.order,
        return_request=return_request,
        refund_number=refund_number,
        currency=return_request.order.currency,
        amount=return_request.refund_amount,
        restocking_fee_deducted=return_request.restocking_fee,
        net_amount=net_amount,
        refund_type=Refund.RefundType.PARTIAL,
        method=method,
        status=Refund.RefundStatus.PENDING,
        reason=f"Return {return_request.return_number}: {return_request.reason}",
        notify_customer=notify_customer,
        created_by=actor,
        restock_items=False,  # Already handled in complete_return_restock
    )

    # ── Create RefundLineItems ──
    for ret_item in return_request.items.select_related("order_item").all():
        line_amount = ret_item.refund_amount or Decimal("0.00")
        if line_amount > 0:
            RefundLineItem.objects.create(
                refund=refund,
                order_item=ret_item.order_item,
                quantity=ret_item.quantity_received or ret_item.quantity,
                amount=line_amount,
                restock=False,
            )

    # ── Update order item quantities ──
    for ret_item in return_request.items.select_related("order_item").all():
        oi = ret_item.order_item
        oi.quantity_returned += ret_item.quantity_received or ret_item.quantity
        oi.quantity_refunded += ret_item.quantity_received or ret_item.quantity
        oi.save(update_fields=["quantity_returned",
                "quantity_refunded", "updated_at"])

    # ── Link return to refund ──
    return_request.refund_id = refund.id
    return_request.status = Return.ReturnStatus.REFUND_PENDING
    return_request.save(update_fields=["refund_id", "status", "updated_at"])

    ReturnEvent.objects.create(
        return_request=return_request,
        from_status=Return.ReturnStatus.RESTOCKED,
        to_status=Return.ReturnStatus.REFUND_PENDING,
        event_note=f"Refund {refund_number} created. Amount: {net_amount}",
        performed_by=actor,
        is_customer_visible=True,
    )

    return RefundResult(
        refund=refund,
        success=True,
        message=f"Refund {refund_number} created. Awaiting processing.",
    )


@transaction.atomic
def create_standalone_refund(
    order,
    amount: Decimal,
    reason: str,
    method: str = "original_payment",
    refund_type: str = "partial",
    line_items: List[dict] = None,
    refund_shipping: bool = False,
    notify_customer: bool = True,
    actor=None,
) -> RefundResult:
    """
    Create a manual refund without a return (e.g. goodwill refund,
    price adjustment, shipping cost refund).

    Args:
        order: Order to refund.
        amount: Total refund amount.
        reason: Internal reason text.
        method: Refund method (original_payment, store_credit, etc.).
        refund_type: Refund type (full, partial, shipping_only, goodwill).
        line_items: Optional [{"order_item_id", "quantity", "amount"}]
        refund_shipping: Include shipping amount in refund.
        notify_customer: Send refund confirmation email.
        actor: Staff user issuing the refund.

    Returns:
        RefundResult.

    Raises:
        RefundError: If order is not refundable or amount exceeds limit.
    """
    from orders.models import Refund, RefundLineItem

    if not order.is_refundable:
        raise RefundError(
            f"Order {order.order_number} is not eligible for a refund "
            f"(financial_status: {order.financial_status})."
        )

    max_refundable = order.total_paid - order.total_refunded
    if amount > max_refundable:
        raise RefundError(
            f"Refund amount {amount} exceeds the maximum refundable "
            f"amount of {max_refundable} for order {order.order_number}."
        )

    shipping_amount = (
        order.total_shipping if refund_shipping else Decimal("0.00")
    )

    refund_number = _generate_refund_number()

    refund = Refund.objects.create(
        order=order,
        return_request=None,
        refund_number=refund_number,
        currency=order.currency,
        amount=amount,
        amount_shipping=shipping_amount,
        restocking_fee_deducted=Decimal("0.00"),
        net_amount=amount,
        refund_type=refund_type,
        method=method,
        status=Refund.RefundStatus.PENDING,
        reason=reason,
        notify_customer=notify_customer,
        created_by=actor,
        restock_items=bool(line_items),
    )

    if line_items:
        for li in line_items:
            from orders.models import OrderItem
            try:
                oi = OrderItem.objects.get(id=li["order_item_id"], order=order)
                RefundLineItem.objects.create(
                    refund=refund,
                    order_item=oi,
                    quantity=li.get("quantity", 1),
                    amount=Decimal(str(li.get("amount", 0))),
                    restock=li.get("restock", False),
                )
            except OrderItem.DoesNotExist:
                logger.warning(
                    "RefundLineItem skipped: item %s not found", li["order_item_id"])

    return RefundResult(
        refund=refund,
        success=True,
        message=f"Refund {refund_number} created. Ready for processing.",
    )


def process_refund(refund, actor=None) -> RefundResult:
    """
    Submit a refund to the payment gateway and update its status.
    This calls the payment gateway API (Stripe, Paystack, etc.)
    and marks the refund as succeeded or failed.

    Returns:
        RefundResult with success flag and gateway response.
    """
    from orders.models import Refund as R

    if refund.status != R.RefundStatus.PENDING:
        raise RefundError(
            f"Refund {refund.refund_number} is not in PENDING status."
        )

    try:
        gateway_result = _call_payment_gateway_refund(refund)

        if gateway_result.get("success"):
            refund.mark_succeeded(
                gateway_refund_id=gateway_result.get("refund_id", ""),
                gateway_response=gateway_result,
            )

            # Update order financial status
            _update_order_financial_status_after_refund(refund.order)

            # Mark return as refunded if linked
            if refund.return_request:
                refund.return_request.status = Return.ReturnStatus.REFUNDED
                refund.return_request.refunded_at = timezone.now()
                refund.return_request.save(
                    update_fields=["status", "refunded_at", "updated_at"])

            logger.info(
                "Refund %s processed successfully. Gateway ref: %s",
                refund.refund_number,
                gateway_result.get("refund_id"),
            )
            return RefundResult(
                refund=refund,
                success=True,
                message="Refund processed successfully.",
                gateway_response=gateway_result,
            )
        else:
            error_msg = gateway_result.get("error", "Unknown gateway error.")
            refund.mark_failed(reason=error_msg)
            return RefundResult(
                refund=refund,
                success=False,
                message=f"Refund failed: {error_msg}",
                gateway_response=gateway_result,
            )

    except Exception as e:
        refund.mark_failed(reason=str(e))
        logger.error("Refund %s failed with exception: %s",
                     refund.refund_number, e)
        return RefundResult(
            refund=refund,
            success=False,
            message=f"Refund processing error: {e}",
        )


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _generate_return_number() -> str:
    from orders.models import Return as R
    with transaction.atomic():
        last = R.objects.select_for_update().order_by(
            "-id").values("return_number").first()
        seq = 1
        if last and last["return_number"]:
            try:
                seq = int(last["return_number"].split("-")[-1]) + 1
            except (ValueError, IndexError):
                pass
        return f"RTN-{seq:06d}"


def _generate_refund_number() -> str:
    from orders.models import Refund as R
    with transaction.atomic():
        last = R.objects.select_for_update().order_by(
            "-id").values("refund_number").first()
        seq = 1
        if last and last["refund_number"]:
            try:
                seq = int(last["refund_number"].split("-")[-1]) + 1
            except (ValueError, IndexError):
                pass
        return f"REF-{seq:06d}"


def _call_payment_gateway_refund(refund) -> dict:
    """
    Stub — replace with real Stripe/Paystack/Flutterwave refund API call.
    Should call the original transaction's gateway.
    """
    logger.info(
        "Gateway refund stub called for refund %s (amount=%s)",
        refund.refund_number, refund.net_amount
    )
    return {
        "success": True,
        "refund_id": f"stub_{refund.id}",
        "amount": str(refund.net_amount),
        "currency": refund.currency,
    }


def _update_order_financial_status_after_refund(order) -> None:
    """Recompute order financial_status after a successful refund."""
    from orders.models import Order

    if order.total_refunded >= order.total_paid:
        order.financial_status = Order.FinancialStatus.REFUNDED
    elif order.total_refunded > 0:
        order.financial_status = Order.FinancialStatus.PARTIALLY_REFUNDED
    order.save(update_fields=["financial_status", "updated_at"])


# Import stub for Return model (avoid circular in type hints)
class Return:
    class ReturnStatus:
        REQUESTED = "requested"
        PENDING_REVIEW = "pending_review"
        APPROVED = "approved"
        RECEIVED = "received"
        INSPECTING = "inspecting"
        RESTOCKED = "restocked"
        REFUND_PENDING = "refund_pending"
        REFUNDED = "refunded"
        REJECTED = "rejected"

    class ReturnItem:
        class ItemDisposition:
            RESTOCK = "restock"
            RESTOCK_AS_USED = "restock_as_used"

    class Refund:
        class RefundType:
            PARTIAL = "partial"
            FULL = "full"

        class RefundStatus:
            PENDING = "pending"
