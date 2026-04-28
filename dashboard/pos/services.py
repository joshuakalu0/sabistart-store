from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import uuid

from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.db.models import F, Q, Sum
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

from public.cart.models import Order, OrderItem, OrderStatusHistory
from public.product.models import Product, ProductVariant

from .models import (
    InventoryAdjustment,
    POSCart,
    POSCartItem,
    POSDiscount,
    POSCatalogItem,
    POSPayment,
    POSProduct,
    POSSession,
    POSTerminal,
    POSTransaction,
    POSTransactionItem,
    Store,
    StoreInventory,
)


MONEY = Decimal("0.01")
QUANTITY = Decimal("0.001")
POS_SCHEMA_REQUIREMENTS = {
    "pos_stores": {"contact_name", "contact_phone", "contact_email", "status"},
    "pos_terminals": {"notes"},
    "pos_sessions": {"expected_cash", "shortage_amount", "overage_amount"},
    "pos_transactions": {"client_transaction_id", "origin_mode", "sync_status", "refunded_amount"},
    "pos_payments": {"amount_received", "balance_returned", "bank_name", "terminal_reference", "custom_payment_label"},
    "pos_cart": {"held_at", "hold_reference"},
}


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def to_quantity(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QUANTITY, rounding=ROUND_HALF_UP)


def get_pos_schema_issues() -> list[dict]:
    issues: list[dict] = []
    introspection = connection.introspection
    try:
        tables = set(introspection.table_names())
        with connection.cursor() as cursor:
            for table_name, required_columns in POS_SCHEMA_REQUIREMENTS.items():
                if table_name not in tables:
                    issues.append(
                        {
                            "table": table_name,
                            "missing_table": True,
                            "missing_columns": sorted(required_columns),
                        }
                    )
                    continue
                existing_columns = {
                    column.name if hasattr(column, "name") else column[0]
                    for column in introspection.get_table_description(cursor, table_name)
                }
                missing_columns = sorted(required_columns - existing_columns)
                if missing_columns:
                    issues.append(
                        {
                            "table": table_name,
                            "missing_table": False,
                            "missing_columns": missing_columns,
                        }
                    )
    except Exception as exc:
        issues.append(
            {
                "table": "schema_introspection",
                "missing_table": False,
                "missing_columns": [],
                "error": str(exc),
            }
        )
    return issues


def get_pos_schema_setup_command() -> str:
    schema_name = getattr(connection, "schema_name", "tenant_schema")
    return f".\\.venv\\Scripts\\python.exe manage.py migrate_schemas --schema={schema_name} --tenant"


def generate_transaction_number() -> str:
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"POS-{timestamp}-{suffix}"


def active_store_queryset():
    return Store.objects.filter(is_active=True, is_deleted=False, status="active")


def active_catalog_item_queryset():
    return POSCatalogItem.objects.filter(
        is_active=True,
        is_deleted=False,
        product__is_deleted=False,
        product__is_active=True,
        product__is_pos_available=True,
    ).filter(
        Q(variant__isnull=True) | Q(variant__is_pos_available=True)
    ).select_related("product", "variant", "product__brand")


def active_product_queryset():
    return POSProduct.objects.filter(is_deleted=False)


def active_inventory_queryset():
    return StoreInventory.objects.filter(
        is_deleted=False,
        store__is_deleted=False,
    ).filter(
        Q(product__isnull=True) | (Q(product__is_deleted=False) & Q(product__is_active=True)),
        Q(catalog_item__isnull=True)
        | (
            Q(catalog_item__is_deleted=False)
            & Q(catalog_item__is_active=True)
            & Q(catalog_item__product__is_active=True)
            & Q(catalog_item__product__is_pos_available=True)
            & (Q(catalog_item__variant__isnull=True) | Q(catalog_item__variant__is_pos_available=True))
        ),
    )


def active_discount_queryset():
    return POSDiscount.objects.filter(is_deleted=False).order_by("name")


@transaction.atomic
def sync_catalog_bridge(*, user=None, published_only: bool = False, include_all_active: bool = False):
    created_items = 0
    updated_items = 0
    products = Product.objects.filter(is_deleted=False, is_active=True)
    if not include_all_active:
        products = products.filter(is_pos_available=True)
    if published_only:
        products = products.filter(status="published")

    for product in products.order_by("name"):
        if product.product_type == "variable":
            variants = ProductVariant.objects.filter(
                product=product,
                is_active=True,
            )
            if not include_all_active:
                variants = variants.filter(is_pos_available=True)
            for variant in variants.order_by("sku"):
                _, created = POSCatalogItem.objects.update_or_create(
                    product=product,
                    variant=variant,
                    defaults={
                        "is_active": True,
                        "created_by": user,
                        "updated_by": user,
                    },
                )
                created_items += int(created)
                updated_items += int(not created)
            continue

        _, created = POSCatalogItem.objects.update_or_create(
            product=product,
            variant=None,
            defaults={
                "is_active": True,
                "created_by": user,
                "updated_by": user,
            },
        )
        created_items += int(created)
        updated_items += int(not created)

    return {
        "created_items": created_items,
        "updated_items": updated_items,
        "total_items": created_items + updated_items,
    }


def generate_order_number() -> tuple[str, int]:
    last_order = (
        Order.objects.select_for_update()
        .order_by("-order_number_sequence")
        .only("order_number_sequence")
        .first()
    )
    sequence = (last_order.order_number_sequence + 1) if last_order else 1
    return f"ORD-{sequence:06d}", sequence


def get_or_create_default_register(*, store: Store, user=None) -> POSTerminal:
    code = f"{store.code}-REG1"[:50]
    terminal, _ = POSTerminal.objects.get_or_create(
        store=store,
        code=code,
        defaults={
            "name": f"{store.name} Front Register"[:120],
            "terminal_type": "browser",
            "is_active": True,
            "created_by": user,
            "updated_by": user,
        },
    )
    return terminal


def get_open_session(*, cashier, store: Store, terminal: POSTerminal | None = None) -> POSSession | None:
    query = POSSession.objects.filter(cashier=cashier, store=store, status="open", is_deleted=False)
    if terminal is not None:
        query = query.filter(terminal=terminal)
    return query.order_by("-opened_at").first()


@transaction.atomic
def open_register_session(*, cashier, store: Store, terminal: POSTerminal, opening_cash=Decimal("0.00"), notes: str = "") -> POSSession:
    existing = get_open_session(cashier=cashier, store=store, terminal=terminal)
    if existing is not None:
        return existing
    return POSSession.objects.create(
        store=store,
        terminal=terminal,
        cashier=cashier,
        opening_cash=to_money(opening_cash),
        notes=notes.strip(),
        created_by=cashier,
        updated_by=cashier,
    )


@transaction.atomic
def close_register_session(*, session: POSSession, closing_cash=Decimal("0.00"), notes: str = "", user=None) -> POSSession:
    if session.status != "open":
        raise ValidationError("This session is already closed.")
    totals = session.transactions.filter(status="completed", is_deleted=False).aggregate(total=Sum("total_amount"))
    cash_totals = session.transactions.filter(
        status="completed",
        payments__payment_method="cash",
        is_deleted=False,
    ).aggregate(total=Sum("payments__amount"))
    expected_cash = to_money(session.opening_cash + (cash_totals["total"] or Decimal("0.00")))
    closing_cash = to_money(closing_cash)
    delta = to_money(closing_cash - expected_cash)
    session.status = "closed"
    session.closed_at = timezone.now()
    session.closing_cash = closing_cash
    session.expected_cash = expected_cash
    session.shortage_amount = abs(delta) if delta < 0 else Decimal("0.00")
    session.overage_amount = delta if delta > 0 else Decimal("0.00")
    session.notes = (session.notes + "\n" + notes.strip()).strip() if notes.strip() else session.notes
    session.save(updated_by=user or session.cashier)
    return session


def _pos_product_image_url(product: POSProduct | None) -> str:
    if product is None or not getattr(product, "image", None):
        return ""
    try:
        return product.image.url
    except Exception:
        return ""


def _catalog_product_image_url(catalog_item: POSCatalogItem | None) -> str:
    if catalog_item is None:
        return ""
    if catalog_item.variant is not None:
        variant_image = catalog_item.variant.images.filter(is_primary=True).first() or catalog_item.variant.images.first()
        if variant_image and getattr(variant_image.image, "url", ""):
            return variant_image.image.url
    product_image = catalog_item.product.images.filter(is_primary=True).first() or catalog_item.product.images.first()
    if product_image and getattr(product_image.image, "url", ""):
        return product_image.image.url
    return ""


def _create_authoritative_order(*, cashier, pos_transaction: POSTransaction):
    platform_actor = None
    platform_user_id = getattr(cashier, "platform_user_id", "") or ""
    if platform_user_id:
        try:
            from system.account.models import PlatformUser

            platform_actor = PlatformUser.objects.filter(pk=platform_user_id).first()
        except Exception:
            platform_actor = None

    order_number, sequence = generate_order_number()
    now = timezone.now()
    order = Order.objects.create(
        order_number=order_number,
        order_number_sequence=sequence,
        customer_email=pos_transaction.customer_email or f"pos-{pos_transaction.transaction_number.lower()}@local.invalid",
        customer_phone=pos_transaction.customer_phone,
        customer_name=pos_transaction.customer_name or "Walk-in Customer",
        status=Order.OrderStatus.COMPLETED,
        financial_status=Order.FinancialStatus.PAID,
        fulfillment_status=Order.FulfillmentStatus.FULFILLED,
        source=Order.OrderSource.POS,
        source_identifier=pos_transaction.transaction_number,
        currency="NGN",
        subtotal_price=pos_transaction.subtotal,
        total_discounts=pos_transaction.discount_amount,
        total_shipping=Decimal("0.00"),
        total_tax=pos_transaction.tax_amount,
        total_price=pos_transaction.total_amount,
        total_outstanding=Decimal("0.00"),
        total_paid=pos_transaction.amount_paid or pos_transaction.total_amount,
        total_refunded=Decimal("0.00"),
        shipping_method_name="POS pickup",
        taxes_included=False,
        customer_note=pos_transaction.notes,
        confirmed_at=now,
        processing_at=now,
        completed_at=now,
        placed_at=pos_transaction.created_at or now,
        send_receipt=bool(pos_transaction.customer_email),
        is_confirmed_by_customer=True,
        buyer_accepts_marketing=False,
        metafields={
            "pos_transaction_id": str(pos_transaction.id),
            "pos_store_id": str(pos_transaction.store_id),
            "pos_store_name": pos_transaction.store.name,
        },
    )

    for item in pos_transaction.items.select_related(
        "store_inventory",
        "store_inventory__catalog_item",
        "store_inventory__catalog_item__product",
        "store_inventory__catalog_item__variant",
        "store_inventory__product",
    ):
        catalog_item = item.catalog_item or item.store_inventory.catalog_item
        variant = catalog_item.variant if catalog_item else None
        product = catalog_item.product if catalog_item else None
        vendor = ""
        if product is not None and product.brand is not None:
            vendor = product.brand.name
        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=int(item.quantity),
            quantity_fulfilled=int(item.quantity),
            quantity_returned=0,
            quantity_refunded=0,
            product_id_snapshot=product.id if product is not None else None,
            variant_id_snapshot=variant.id if variant is not None else None,
            product_title=item.product_name,
            variant_title=variant.variant_name if variant is not None else "",
            sku=item.product_sku,
            barcode=item.product_barcode,
            vendor=vendor,
            product_image_url=_catalog_product_image_url(catalog_item),
            unit_price=item.unit_price,
            compare_at_price=None,
            unit_discount=to_money(item.discount_amount / item.quantity) if item.quantity else Decimal("0.00"),
            unit_tax=to_money(item.tax_amount / item.quantity) if item.quantity else Decimal("0.00"),
            tax_rate=item.tax_rate,
            total_discount=item.discount_amount,
            total_tax=item.tax_amount,
            subtotal=to_money(item.line_total - item.tax_amount),
            total=item.line_total,
            cost_per_item=item.store_inventory.effective_cost_price,
            tax_lines=[{"title": "POS Tax", "rate": str(item.tax_rate), "amount": str(item.tax_amount)}] if item.tax_amount else [],
            is_taxable=item.tax_rate > 0,
            fulfillment_service="pos",
            requires_shipping=False,
            is_gift_card=False,
            weight=(product.weight if product is not None else None),
            custom_properties={
                "pos_transaction_number": pos_transaction.transaction_number,
                "pos_store": pos_transaction.store.name,
            },
            applied_discount_ids=[],
        )

    OrderStatusHistory.objects.create(
        order=order,
        from_status="",
        to_status=order.status,
        financial_status_snapshot=order.financial_status,
        fulfillment_status_snapshot=order.fulfillment_status,
        source=OrderStatusHistory.ChangeSource.STAFF,
        changed_by=platform_actor,
        note=f"Created from POS transaction {pos_transaction.transaction_number}",
        is_customer_visible=False,
    )
    return order


def create_pos_product(*, user, store: Store, payload: dict, image_file=None) -> POSProduct:
    sku = (payload.get("sku") or "").strip()
    barcode = (payload.get("barcode") or "").strip()
    stock_quantity = int(payload.get("stock_quantity") or 0)

    if not payload.get("name"):
        raise ValidationError("Product name is required.")
    if not sku:
        raise ValidationError("SKU is required.")
    if stock_quantity < 0:
        raise ValidationError("Opening stock cannot be negative.")

    if POSProduct.objects.filter(sku__iexact=sku).exists():
        raise ValidationError("A POS product with this SKU already exists.")
    if barcode and POSProduct.objects.filter(barcode__iexact=barcode).exists():
        raise ValidationError("A POS product with this barcode already exists.")

    return POSProduct.objects.create(
        name=payload["name"].strip(),
        image=image_file,
        sku=sku,
        barcode=barcode,
        product_type=payload.get("product_type") or "simple",
        description=(payload.get("description") or "").strip(),
        cost_price=to_money(payload.get("selling_price")),
        selling_price=to_money(payload.get("selling_price")),
        is_taxable=bool(payload.get("is_taxable", True)),
        tax_rate=payload.get("tax_rate") or None,
        category=(payload.get("category") or "").strip(),
        brand=(payload.get("brand") or "").strip(),
        is_active=bool(payload.get("is_active", True)),
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def create_quick_pos_product(*, user, store: Store, payload: dict, image_file=None) -> tuple[POSProduct, StoreInventory]:
    product = create_pos_product(user=user, store=store, payload=payload, image_file=image_file)
    inventory = StoreInventory.objects.create(
        store=store,
        product=product,
        quantity=int(payload.get("stock_quantity") or 0),
        low_stock_threshold=5,
        created_by=user,
        updated_by=user,
    )
    return product, inventory


@transaction.atomic
def update_quick_pos_product(*, product: POSProduct, store: Store, payload: dict, user, image_file=None) -> tuple[POSProduct, StoreInventory]:
    barcode = (payload.get("barcode") or "").strip()
    stock_quantity = int(payload.get("stock_quantity") or 0)
    if stock_quantity < 0:
        raise ValidationError("Stock cannot be negative.")
    duplicate_qs = POSProduct.objects.exclude(pk=product.pk)
    if barcode and duplicate_qs.filter(barcode__iexact=barcode).exists():
        raise ValidationError("A POS product with this barcode already exists.")

    product.name = (payload.get("name") or "").strip()
    product.description = (payload.get("description") or "").strip()
    product.barcode = barcode
    product.selling_price = to_money(payload.get("selling_price"))
    product.cost_price = product.selling_price
    if image_file is not None:
        product.image = image_file
    product.save(updated_by=user)

    inventory, _ = StoreInventory.objects.get_or_create(
        store=store,
        product=product,
        defaults={
            "quantity": stock_quantity,
            "created_by": user,
            "updated_by": user,
        },
    )
    inventory.quantity = stock_quantity
    inventory.save(updated_by=user)
    return product, inventory


def toggle_product_status(*, product: POSProduct, user):
    product.is_active = not product.is_active
    product.save(updated_by=user)
    return product


def search_store_products(*, store: Store, query: str, limit: int = 20):
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return []

    inventory_items = (
        active_inventory_queryset()
        .select_related("product", "catalog_item", "catalog_item__product", "catalog_item__variant", "store")
        .filter(
            store=store,
            quantity__gt=0,
        )
        .filter(
            Q(product__name__icontains=cleaned_query)
            | Q(product__sku__icontains=cleaned_query)
            | Q(product__barcode__icontains=cleaned_query)
            | Q(catalog_item__product__name__icontains=cleaned_query)
            | Q(catalog_item__variant__variant_name__icontains=cleaned_query)
            | Q(catalog_item__product__sku__icontains=cleaned_query)
            | Q(catalog_item__variant__sku__icontains=cleaned_query)
            | Q(catalog_item__barcode_override__icontains=cleaned_query)
        )
        .order_by("product__name")[:limit]
    )

    products = []
    for item in inventory_items:
        if item.available_quantity <= 0:
            continue
        products.append(
            {
                "id": str(item.id),
                "name": item.display_name,
                "sku": item.display_sku,
                "barcode": item.display_barcode,
                "price": float(item.effective_selling_price),
                "quantity": item.available_quantity,
                "store": item.store.name,
                "image_url": _pos_product_image_url(item.product) or _catalog_product_image_url(item.catalog_item),
            }
        )
    return products


@transaction.atomic
def adjust_inventory(
    *,
    inventory: StoreInventory,
    adjustment_type: str,
    quantity_change: int,
    reason: str,
    user,
    reference_number: str = "",
):
    if quantity_change == 0:
        raise ValidationError("Quantity change cannot be zero.")
    if adjustment_type not in dict(InventoryAdjustment.ADJUSTMENT_TYPE):
        raise ValidationError("Invalid adjustment type.")
    if not reason.strip():
        raise ValidationError("A reason is required for inventory adjustments.")

    locked_inventory = (
        StoreInventory.objects.select_for_update()
        .get(pk=inventory.pk)
    )
    old_quantity = locked_inventory.quantity
    new_quantity = old_quantity + quantity_change

    if new_quantity < 0:
        raise ValidationError("This adjustment would reduce stock below zero.")

    locked_inventory.quantity = new_quantity
    if adjustment_type == "restock" and quantity_change > 0:
        locked_inventory.last_restocked = timezone.now()
    locked_inventory.save(updated_by=user)

    adjustment = InventoryAdjustment.objects.create(
        store_inventory=locked_inventory,
        adjustment_type=adjustment_type,
        quantity_before=old_quantity,
        quantity_change=quantity_change,
        quantity_after=new_quantity,
        reason=reason.strip(),
        reference_number=reference_number.strip(),
        created_by=user,
        updated_by=user,
    )
    return locked_inventory, adjustment


@transaction.atomic
def create_sale_transaction(
    *,
    cashier,
    store: Store,
    items_data: list[dict],
    payment_method: str,
    customer_name: str = "",
    customer_email: str = "",
    customer_phone: str = "",
    notes: str = "",
    session: POSSession | None = None,
    terminal: POSTerminal | None = None,
    origin_mode: str = "online",
    client_transaction_id: str = "",
    payments_data: list[dict] | None = None,
):
    if not items_data:
        raise ValidationError("Add at least one product before completing the sale.")
    if payment_method not in dict(POSPayment.PAYMENT_METHOD):
        raise ValidationError("Unsupported payment method.")
    if session is None:
        raise ValidationError("An open register session is required before processing a sale.")

    pos_transaction = POSTransaction.objects.create(
        store=store,
        cashier=cashier,
        session=session,
        terminal=terminal,
        transaction_number=generate_transaction_number(),
        client_transaction_id=client_transaction_id,
        transaction_type="sale",
        status="pending",
        origin_mode=origin_mode,
        sync_status="not_required" if origin_mode == "online" else "queued",
        customer_name=customer_name.strip(),
        customer_email=customer_email.strip(),
        customer_phone=customer_phone.strip(),
        subtotal=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
        amount_paid=Decimal("0.00"),
        notes=notes.strip(),
        created_by=cashier,
        updated_by=cashier,
    )

    subtotal = Decimal("0.00")
    tax_amount = Decimal("0.00")
    discount_amount = Decimal("0.00")

    for item_data in items_data:
        inventory_id = item_data.get("inventory_id")
        quantity = to_quantity(item_data.get("quantity"))
        if quantity <= 0:
            raise ValidationError("Item quantities must be greater than zero.")
        if quantity != quantity.to_integral_value():
            raise ValidationError("POS inventory only supports whole-number quantities.")

        inventory = (
            StoreInventory.objects.select_for_update()
            .get(pk=inventory_id, store=store, is_deleted=False)
        )
        if inventory.product is not None and not inventory.product.is_active:
            raise ValidationError(f"{inventory.product.name} is inactive and cannot be sold.")
        if inventory.catalog_item is not None and (
            not inventory.catalog_item.is_active
            or not inventory.catalog_item.product.is_active
            or not inventory.catalog_item.product.is_pos_available
            or (inventory.catalog_item.variant is not None and not inventory.catalog_item.variant.is_pos_available)
        ):
            raise ValidationError(f"{inventory.catalog_item.display_name} is inactive and cannot be sold.")

        int_quantity = int(quantity)
        if inventory.available_quantity < int_quantity:
            raise ValidationError(f"Insufficient stock for {inventory.display_name}.")

        unit_price = to_money(inventory.effective_selling_price)
        line_subtotal = to_money(unit_price * quantity)
        item_discount = to_money(item_data.get("discount_amount"))

        applicable_tax_rate = Decimal("0.0000")
        if inventory.is_taxable:
            applicable_tax_rate = (
                inventory.product.tax_rate
                if inventory.product is not None and inventory.product.tax_rate is not None
                else store.tax_rate
            ) or Decimal("0.0000")

        line_tax = to_money((line_subtotal - item_discount) * applicable_tax_rate)
        line_total = to_money(line_subtotal - item_discount + line_tax)

        POSTransactionItem.objects.create(
            transaction=pos_transaction,
            store_inventory=inventory,
            catalog_item=inventory.catalog_item,
            product_name=inventory.display_name,
            product_sku=inventory.display_sku,
            product_barcode=inventory.display_barcode,
            unit_price=unit_price,
            quantity=quantity,
            discount_amount=item_discount,
            line_total=line_total,
            tax_rate=applicable_tax_rate,
            tax_amount=line_tax,
            created_by=cashier,
            updated_by=cashier,
        )

        old_quantity = inventory.quantity
        inventory.quantity = old_quantity - int_quantity
        inventory.last_sold = timezone.now()
        inventory.save(updated_by=cashier)

        InventoryAdjustment.objects.create(
            store_inventory=inventory,
            adjustment_type="sale",
            quantity_before=old_quantity,
            quantity_change=-int_quantity,
            quantity_after=inventory.quantity,
            reason=f"Sale recorded under {pos_transaction.transaction_number}",
            reference_number=pos_transaction.transaction_number,
            created_by=cashier,
            updated_by=cashier,
        )

        subtotal += line_subtotal
        tax_amount += line_tax
        discount_amount += item_discount

    total_amount = to_money(subtotal - discount_amount + tax_amount)
    payment_rows = payments_data or [{"payment_method": payment_method, "amount": total_amount}]
    total_paid = Decimal("0.00")
    cash_received = Decimal("0.00")
    for payment_row in payment_rows:
        method = payment_row.get("payment_method", payment_method)
        if method not in dict(POSPayment.PAYMENT_METHOD):
            raise ValidationError("Unsupported payment method.")
        amount = to_money(payment_row.get("amount", total_amount))
        total_paid += amount
        amount_received = payment_row.get("amount_received")
        if method == "cash":
            cash_received += to_money(amount_received if amount_received is not None else amount)
        POSPayment.objects.create(
            transaction=pos_transaction,
            payment_method=method,
            amount=amount,
            status="completed",
            processed_at=timezone.now(),
            reference_number=str(payment_row.get("reference_number", "")).strip(),
            bank_name=str(payment_row.get("bank_name", "")).strip(),
            terminal_reference=str(payment_row.get("terminal_reference", "")).strip(),
            custom_payment_label=str(payment_row.get("custom_payment_label", "")).strip(),
            amount_received=to_money(amount_received) if amount_received not in (None, "") else None,
            balance_returned=to_money(payment_row.get("balance_returned")) if payment_row.get("balance_returned") not in (None, "") else None,
            processor_response=payment_row.get("processor_response", {}),
            created_by=cashier,
            updated_by=cashier,
        )
    if total_paid < total_amount:
        raise ValidationError("Total paid is less than the sale total.")
    change_amount = to_money(cash_received - total_amount) if cash_received > total_amount else Decimal("0.00")

    pos_transaction.subtotal = to_money(subtotal)
    pos_transaction.tax_amount = to_money(tax_amount)
    pos_transaction.discount_amount = to_money(discount_amount)
    pos_transaction.total_amount = total_amount
    pos_transaction.amount_paid = to_money(total_paid)
    pos_transaction.change_amount = change_amount
    pos_transaction.status = "completed"
    pos_transaction.sync_status = "synced" if origin_mode in {"offline", "synced"} else "not_required"
    pos_transaction.authoritative_order = _create_authoritative_order(
        cashier=cashier,
        pos_transaction=pos_transaction,
    )
    pos_transaction.save(updated_by=cashier)
    send_receipt_email(pos_transaction)
    return pos_transaction


def build_inventory_summary(inventory_qs):
    totals = inventory_qs.aggregate(total_units=Sum("quantity"))
    low_stock_qs = inventory_qs.filter(
        quantity__gt=0,
        quantity__lte=F("low_stock_threshold"),
    )
    out_of_stock_qs = inventory_qs.filter(quantity=0)
    return {
        "total_products": inventory_qs.count(),
        "total_units": totals["total_units"] or 0,
        "low_stock_items": low_stock_qs,
        "out_of_stock_items": out_of_stock_qs,
        "low_stock_count": low_stock_qs.count(),
        "out_of_stock_count": out_of_stock_qs.count(),
    }


def build_receipt_context(transaction: POSTransaction):
    items = transaction.items.select_related(
        "store_inventory",
        "store_inventory__product",
        "store_inventory__catalog_item",
        "store_inventory__catalog_item__product",
        "catalog_item",
        "catalog_item__product",
    )
    payments = transaction.payments.all()
    return {
        "transaction": transaction,
        "items": items,
        "payments": payments,
        "store": transaction.store,
    }


def send_receipt_email(transaction: POSTransaction) -> bool:
    if not transaction.customer_email:
        return False
    context = build_receipt_context(transaction)
    context["receipt_url"] = ""
    html_body = render_to_string("dashboard/pos/receipt_email.html", context)
    text_body = strip_tags(html_body)
    subject = f"Invoice for {transaction.transaction_number}"
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        to=[transaction.customer_email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)
    return True


# ─────────────────────────────────────────────────────────────
# CART SERVICES
# ─────────────────────────────────────────────────────────────

def get_or_create_active_cart(*, cashier, store) -> POSCart:
    """
    Return the single OPEN cart for this cashier × store, creating one if none exists.

    Only one OPEN cart per cashier-store pair is enforced — completed/voided carts
    are left in place for audit purposes.
    """
    cart = (
        POSCart.objects.filter(cashier=cashier, store=store, status=POSCart.Status.OPEN)
        .order_by("-created_at")
        .first()
    )
    if cart is None:
        cart = POSCart.objects.create(cashier=cashier, store=store)
    return cart


def add_item_to_cart(*, cart: POSCart, inventory_id: str, store: Store) -> POSCartItem:
    """
    Add one unit of an inventory item to the cart, or increment its quantity if
    already present.  The ``unit_price`` is snapshotted from StoreInventory at
    this moment so subsequent price changes do not affect this cart.

    Raises ValidationError if:
      - The inventory item is not found for this store.
      - Stock is already at or below zero.
      - The cart is not OPEN.
    """
    if not cart.is_open:
        raise ValidationError("Cannot add items to a cart that is not open.")

    try:
        inventory = StoreInventory.objects.select_related(
            "catalog_item", "catalog_item__product"
        ).get(id=inventory_id, store=store)
    except StoreInventory.DoesNotExist:
        raise ValidationError("Product not found in this store's inventory.")

    if inventory.quantity <= 0:
        raise ValidationError(f"'{inventory.display_name}' is out of stock.")

    unit_price = inventory.effective_selling_price
    catalog_item = inventory.catalog_item

    # Check if the item is already in this cart
    existing = POSCartItem.objects.filter(
        cart=cart, store_inventory=inventory
    ).first()

    if existing:
        max_qty = inventory.quantity
        if existing.quantity >= max_qty:
            raise ValidationError(
                f"Cannot add more — only {max_qty} unit(s) of '{inventory.display_name}' in stock."
            )
        existing.quantity += 1
        existing.save()
        return existing

    name = (
        (catalog_item.name if catalog_item else None)
        or getattr(inventory, "display_name", "")
        or "Unknown product"
    )
    sku = (catalog_item.sku if catalog_item else None) or ""

    item = POSCartItem.objects.create(
        cart=cart,
        store_inventory=inventory,
        catalog_item=catalog_item,
        product_name=name,
        product_sku=sku,
        unit_price=unit_price,
        quantity=1,
    )
    return item


def update_cart_item_quantity(*, cart_item: POSCartItem, quantity: int) -> POSCartItem:
    """
    Set the quantity of a cart item.  Pass 0 to remove it.

    Raises ValidationError if:
      - The cart is not OPEN.
      - Requested quantity exceeds available stock.
    """
    if not cart_item.cart.is_open:
        raise ValidationError("Cannot modify a cart that is not open.")

    if quantity <= 0:
        cart_item.delete()
        return cart_item

    if cart_item.store_inventory:
        available = cart_item.store_inventory.quantity
        if quantity > available:
            raise ValidationError(
                f"Only {available} unit(s) of '{cart_item.product_name}' in stock."
            )

    cart_item.quantity = quantity
    cart_item.save()
    return cart_item


def remove_cart_item(*, cart_item: POSCartItem) -> None:
    """Remove a single item from the cart."""
    if not cart_item.cart.is_open:
        raise ValidationError("Cannot modify a cart that is not open.")
    cart_item.delete()


def clear_cart(*, cart: POSCart) -> None:
    """Remove ALL items from the cart, leaving it open and empty."""
    if not cart.is_open:
        raise ValidationError("Cannot clear a cart that is not open.")
    cart.items.all().delete()


@transaction.atomic
def hold_cart(*, cart: POSCart, reference: str = "") -> POSCart:
    if not cart.is_open:
        raise ValidationError("Only open carts can be held.")
    if cart.items.count() == 0:
        raise ValidationError("Cannot hold an empty cart.")
    cart.status = POSCart.Status.HELD
    cart.hold_reference = reference.strip() or uuid.uuid4().hex[:8].upper()
    cart.held_at = timezone.now()
    cart.save(update_fields=["status", "hold_reference", "held_at", "updated_at"])
    return cart


@transaction.atomic
def resume_cart(*, cart: POSCart) -> POSCart:
    if cart.status != POSCart.Status.HELD:
        raise ValidationError("Only held carts can be resumed.")
    cart.status = POSCart.Status.OPEN
    cart.save(update_fields=["status", "updated_at"])
    return cart


@transaction.atomic
def void_cart(*, cart: POSCart) -> POSCart:
    if cart.status not in {POSCart.Status.OPEN, POSCart.Status.HELD}:
        raise ValidationError("Only open or held carts can be cleared.")
    cart.items.all().delete()
    cart.status = POSCart.Status.VOIDED
    cart.voided_at = timezone.now()
    cart.save(update_fields=["status", "voided_at", "updated_at"])
    return cart


@transaction.atomic
def checkout_cart(
    *,
    cart: POSCart,
    payment_method: str,
    customer_name: str = "",
    customer_email: str = "",
    customer_phone: str = "",
    notes: str = "",
    cashier=None,
    session: POSSession | None = None,
    terminal: POSTerminal | None = None,
    payments_data: list[dict] | None = None,
    origin_mode: str = "online",
    client_transaction_id: str = "",
) -> POSTransaction:
    """
    Atomically check out the cart:

    1. Validates the cart is OPEN and has items.
    2. Builds the ``items`` payload expected by ``create_sale_transaction()``.
    3. Calls the existing atomic service (which validates stock, deducts inventory,
       creates POSTransaction + POSTransactionItem, records payment, etc.).
    4. Marks the cart COMPLETED and links it to the resulting transaction.

    Returns the completed POSTransaction.
    Raises ValidationError on any stock or validation failure (the whole operation
    is rolled back automatically by the @transaction.atomic decorator).
    """
    if not cart.is_open:
        raise ValidationError("This cart is already completed or voided.")

    cart_items = list(cart.items.select_related("store_inventory").all())
    if not cart_items:
        raise ValidationError("Cannot check out an empty cart.")

    items_payload = [
        {
            "inventory_id": str(item.store_inventory_id),
            "quantity": item.quantity,
        }
        for item in cart_items
        if item.store_inventory_id
    ]

    if not items_payload:
        raise ValidationError("No valid inventory items found in cart.")

    txn = create_sale_transaction(
        cashier=cashier or cart.cashier,
        store=cart.store,
        items_data=items_payload,
        payment_method=payment_method,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        notes=notes,
        session=session,
        terminal=terminal,
        origin_mode=origin_mode,
        client_transaction_id=client_transaction_id,
        payments_data=payments_data,
    )

    # Mark cart complete and link to transaction
    cart.status = POSCart.Status.COMPLETED
    cart.transaction = txn
    cart.completed_at = timezone.now()
    cart.save(update_fields=["status", "transaction", "completed_at", "updated_at"])

    return txn


@transaction.atomic
def refund_transaction(*, transaction: POSTransaction, cashier, reason: str = "") -> POSTransaction:
    if transaction.status not in {"completed", "partially_refunded"}:
        raise ValidationError("Only completed transactions can be refunded.")
    refund = POSTransaction.objects.create(
        store=transaction.store,
        cashier=cashier,
        session=transaction.session,
        terminal=transaction.terminal,
        transaction_number=generate_transaction_number(),
        transaction_type="refund",
        status="completed",
        customer_name=transaction.customer_name,
        customer_email=transaction.customer_email,
        customer_phone=transaction.customer_phone,
        subtotal=transaction.subtotal,
        tax_amount=transaction.tax_amount,
        discount_amount=transaction.discount_amount,
        total_amount=transaction.total_amount,
        amount_paid=Decimal("0.00"),
        change_amount=Decimal("0.00"),
        refunded_amount=transaction.total_amount,
        original_transaction=transaction,
        notes=(reason or f"Refund for {transaction.transaction_number}").strip(),
        created_by=cashier,
        updated_by=cashier,
    )
    for item in transaction.items.select_related("store_inventory", "catalog_item"):
        inventory = item.store_inventory
        if inventory:
            before = inventory.quantity
            inventory.quantity = before + int(item.quantity)
            inventory.save(updated_by=cashier)
            InventoryAdjustment.objects.create(
                store_inventory=inventory,
                adjustment_type="reconciliation",
                quantity_before=before,
                quantity_change=int(item.quantity),
                quantity_after=inventory.quantity,
                reason=f"Refund recorded under {refund.transaction_number}",
                reference_number=refund.transaction_number,
                created_by=cashier,
                updated_by=cashier,
            )
        POSTransactionItem.objects.create(
            transaction=refund,
            store_inventory=item.store_inventory,
            catalog_item=item.catalog_item,
            product_name=item.product_name,
            product_sku=item.product_sku,
            product_barcode=item.product_barcode,
            unit_price=item.unit_price,
            quantity=item.quantity,
            discount_amount=item.discount_amount,
            line_total=item.line_total,
            tax_rate=item.tax_rate,
            tax_amount=item.tax_amount,
            created_by=cashier,
            updated_by=cashier,
        )
    for payment in transaction.payments.all():
        POSPayment.objects.create(
            transaction=refund,
            payment_method=payment.payment_method,
            amount=payment.amount,
            status="refunded",
            reference_number=payment.reference_number,
            bank_name=payment.bank_name,
            terminal_reference=payment.terminal_reference,
            custom_payment_label=payment.custom_payment_label,
            created_by=cashier,
            updated_by=cashier,
        )
    transaction.refunded_amount = to_money(transaction.refunded_amount + transaction.total_amount)
    transaction.status = "refunded"
    transaction.save(update_fields=["refunded_amount", "status", "updated_at"])
    return refund


def sync_offline_transaction(*, cashier, store: Store, terminal: POSTerminal, session: POSSession, payload: dict) -> POSTransaction:
    client_transaction_id = str(payload.get("client_transaction_id", "")).strip()
    if not client_transaction_id:
        raise ValidationError("client_transaction_id is required for offline sync.")
    existing = POSTransaction.objects.filter(client_transaction_id=client_transaction_id).first()
    if existing is not None:
        return existing
    return create_sale_transaction(
        cashier=cashier,
        store=store,
        session=session,
        terminal=terminal,
        items_data=payload.get("items", []),
        payment_method=payload.get("payment_method", "cash"),
        customer_name=payload.get("customer_name", ""),
        customer_email=payload.get("customer_email", ""),
        customer_phone=payload.get("customer_phone", ""),
        notes=payload.get("notes", ""),
        origin_mode="synced",
        client_transaction_id=client_transaction_id,
        payments_data=payload.get("payments", []),
    )


def get_cart_context(cart: POSCart) -> dict:
    """Return a serialisable dict representing the cart (for JSON API responses)."""
    items = list(cart.items.select_related("store_inventory").order_by("created_at"))
    subtotal = sum(i.line_total for i in items) or Decimal("0.00")
    return {
        "cart_id": str(cart.id),
        "status": cart.status,
        "item_count": len(items),
        "subtotal": float(subtotal),
        "items": [
            {
                "id": str(item.id),
                "inventory_id": str(item.store_inventory_id) if item.store_inventory_id else None,
                "product_name": item.product_name,
                "product_sku": item.product_sku,
                "unit_price": float(item.unit_price),
                "quantity": item.quantity,
                "line_total": float(item.line_total),
                "max_quantity": item.store_inventory.quantity if item.store_inventory else item.quantity,
            }
            for item in items
        ],
    }
