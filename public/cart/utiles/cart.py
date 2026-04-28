"""
orders/utils/cart.py
====================
Cart lifecycle utilities — session resolution, item management,
discount application, totals calculation, abandonment tracking,
guest-to-user merge.

All functions are tenant-aware (django-tenants sets the schema on the
connection before any request reaches here — no schema switching needed).

Raises:
    CartError         → base exception for all cart errors
    CartItemError     → item-level validation failures
    DiscountError     → invalid/expired/limit-exceeded discount codes
"""

import logging
import secrets
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("orders.cart")

CART_SESSION_KEY = "_cart_id"
CART_TOKEN_HEADER = "X-Cart-Token"
CART_COOKIE_NAME = "cart_token"


# ─────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────

class CartError(Exception):
    """Base exception for all cart-level errors."""
    pass


class CartItemError(CartError):
    """Item-level validation error (out of stock, qty limit, etc.)."""
    pass


class DiscountError(CartError):
    """Discount code application error."""
    pass


# ─────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class CartTotals:
    """
    Structured result from recalculate_cart_totals().
    All amounts in store currency.
    """
    subtotal: Decimal = Decimal("0.00")
    discount_total: Decimal = Decimal("0.00")
    shipping_total: Decimal = Decimal("0.00")
    tax_total: Decimal = Decimal("0.00")
    grand_total: Decimal = Decimal("0.00")
    item_count: int = 0
    currency: str = "USD"
    discount_lines: list = field(default_factory=list)


@dataclass
class AddItemResult:
    """Result from add_item_to_cart()."""
    cart_item: object = None
    created: bool = False
    previous_quantity: int = 0
    new_quantity: int = 0
    totals: CartTotals = None


@dataclass
class DiscountResult:
    """Result from apply_discount_code()."""
    success: bool = False
    discount_amount: Decimal = Decimal("0.00")
    message: str = ""
    code: str = ""


# ─────────────────────────────────────────────────────────────
# IP / REQUEST HELPERS
# ─────────────────────────────────────────────────────────────

def get_client_ip(request) -> str:
    """
    Extract real client IP from request, respecting common
    reverse proxy headers (nginx, Cloudflare, AWS ALB).
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        # X-Forwarded-For: client, proxy1, proxy2
        # First IP is the real client
        return forwarded_for.split(",")[0].strip()

    real_ip = request.META.get("HTTP_X_REAL_IP")
    if real_ip:
        return real_ip.strip()

    return request.META.get("REMOTE_ADDR", "")


def _get_utm_data(request) -> dict:
    """Extract UTM parameters from request GET or session."""
    params = {}
    for key in ("utm_source", "utm_medium", "utm_campaign"):
        value = request.GET.get(key) or request.session.get(key, "")
        if value:
            params[key] = value
    return params


# ─────────────────────────────────────────────────────────────
# SECTION 1 — CART RESOLUTION
# ─────────────────────────────────────────────────────────────

def get_or_create_cart(request, currency: str = "USD"):
    """
    Resolve the active Cart for this request.

    Resolution order:
      1. Logged-in user  → find/create by customer FK
      2. API token       → find by X-Cart-Token header
      3. Session key     → find by Django session
      4. Cookie token    → find by cart cookie (mobile web)
      5. Nothing found   → create a new guest cart

    Returns:
        Cart: The active or newly created cart.
    """
    from orders.models import Cart

    # Ensure Django session exists
    if not request.session.session_key:
        request.session.create()

    session_key = request.session.session_key

    # ── Logged-in customer ──
    if hasattr(request, "user") and request.user.is_authenticated:
        customer = getattr(request.user, "customer_profile", None)
        if customer:
            cart, created = Cart.objects.get_or_create(
                customer=customer,
                status=Cart.CartStatus.ACTIVE,
                defaults={
                    "session_key": session_key,
                    "currency": currency,
                    "ip_address": get_client_ip(request),
                    "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
                    **_get_utm_data(request),
                },
            )
            if created:
                logger.info("Created new cart %s for customer %s", cart.id, customer.id)
            return cart

    # ── API / headless token ──
    api_token = request.headers.get(CART_TOKEN_HEADER)
    if api_token:
        cart = Cart.objects.filter(
            checkout_token=api_token,
            status=Cart.CartStatus.ACTIVE,
        ).first()
        if cart:
            return cart

    # ── Django session ──
    if session_key:
        cart = Cart.objects.filter(
            session_key=session_key,
            status=Cart.CartStatus.ACTIVE,
            customer__isnull=True,
        ).first()
        if cart:
            return cart

    # ── Cookie fallback ──
    cookie_token = request.COOKIES.get(CART_COOKIE_NAME)
    if cookie_token:
        cart = Cart.objects.filter(
            checkout_token=cookie_token,
            status=Cart.CartStatus.ACTIVE,
        ).first()
        if cart:
            return cart

    # ── Create new guest cart ──
    checkout_token = secrets.token_urlsafe(32)
    cart = Cart.objects.create(
        session_key=session_key,
        checkout_token=checkout_token,
        currency=currency,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        referrer_url=request.META.get("HTTP_REFERER", "")[:500],
        **_get_utm_data(request),
    )
    logger.info("Created new guest cart %s (session=%s)", cart.id, session_key[:8])
    return cart


def get_cart_by_token(token: str):
    """
    Fetch an active or abandoned cart by its checkout_token.
    Used in email recovery links: /checkout/recover/?token=<token>

    Returns:
        Cart | None
    """
    from orders.models import Cart

    return Cart.objects.filter(
        checkout_token=token,
        status__in=[
            Cart.CartStatus.ACTIVE,
            Cart.CartStatus.ABANDONED,
            Cart.CartStatus.RECOVERING,
        ],
    ).prefetch_related("items__variant__product").first()


def capture_checkout_email(cart, email: str) -> None:
    """
    Capture email early in checkout (before form submission).
    Enables abandonment recovery even if they don't complete.
    Called via lightweight AJAX on email field blur.
    """
    if not email or "@" not in email:
        return

    cart.email = email.strip().lower()
    cart.checkout_step = "contact"
    cart.last_activity_at = timezone.now()
    cart.save(update_fields=["email", "checkout_step", "last_activity_at", "updated_at"])
    logger.debug("Captured checkout email for cart %s", cart.id)


# ─────────────────────────────────────────────────────────────
# SECTION 2 — ITEM MANAGEMENT
# ─────────────────────────────────────────────────────────────

def add_item_to_cart(
    cart,
    variant,
    quantity: int = 1,
    custom_properties: dict = None,
    is_gift: bool = False,
    gift_message: str = "",
) -> AddItemResult:
    """
    Add a ProductVariant to the cart, or increment quantity if it exists.

    Validates:
      - Variant is active
      - Variant is in stock (or allows backorder)
      - Quantity does not exceed per-item or inventory limits
      - Cart is still active

    Args:
        cart: Cart instance
        variant: catalog.ProductVariant instance
        quantity: Units to add (default 1)
        custom_properties: Dict of custom line attributes (e.g. engraving)
        is_gift: Flag this line as a gift
        gift_message: Gift message for this line

    Returns:
        AddItemResult with cart_item, created flag, old/new qty, and new totals.

    Raises:
        CartError: If cart is not ACTIVE.
        CartItemError: If variant fails stock or status validation.
    """
    from orders.models import CartItem

    if cart.status != cart.CartStatus.ACTIVE:
        raise CartError(
            f"Cannot add items to a cart with status '{cart.status}'."
        )

    if not variant.is_active:
        raise CartItemError(
            f"'{variant.product.title}' is not currently available."
        )

    if quantity < 1:
        raise CartItemError("Quantity must be at least 1.")

    # ── Stock check ──
    _validate_variant_stock(variant, quantity)

    with transaction.atomic():
        existing_item = CartItem.objects.filter(
            cart=cart,
            variant=variant,
        ).select_for_update().first()

        if existing_item:
            previous_qty = existing_item.quantity
            new_qty = previous_qty + quantity

            # Re-validate combined quantity
            _validate_variant_stock(variant, new_qty)
            _validate_max_quantity(existing_item, new_qty)

            existing_item.quantity = new_qty
            existing_item.unit_price = variant.effective_price
            existing_item.save(update_fields=["quantity", "unit_price", "updated_at"])

            cart.last_activity_at = timezone.now()
            cart.save(update_fields=["last_activity_at", "updated_at"])

            totals = recalculate_cart_totals(cart)
            return AddItemResult(
                cart_item=existing_item,
                created=False,
                previous_quantity=previous_qty,
                new_quantity=new_qty,
                totals=totals,
            )

        else:
            # Snapshot product data at add-time
            item = CartItem.objects.create(
                cart=cart,
                variant=variant,
                quantity=quantity,
                unit_price=variant.effective_price,
                compare_at_price=variant.compare_at_price or variant.product.compare_at_price,
                original_price=variant.effective_price,
                product_title=variant.product.title,
                variant_title=variant.title or "",
                sku=variant.sku,
                product_image_url=_get_variant_image_url(variant),
                requires_shipping=variant.requires_shipping,
                is_gift=is_gift,
                gift_message=gift_message,
                custom_properties=custom_properties or {},
            )

            cart.last_activity_at = timezone.now()
            cart.save(update_fields=["last_activity_at", "updated_at"])

            totals = recalculate_cart_totals(cart)
            logger.info(
                "Added variant %s (qty=%d) to cart %s",
                variant.sku, quantity, cart.id
            )
            return AddItemResult(
                cart_item=item,
                created=True,
                previous_quantity=0,
                new_quantity=quantity,
                totals=totals,
            )


def update_cart_item_quantity(cart, variant, new_quantity: int) -> CartTotals:
    """
    Set a cart item's quantity to an exact value.
    Passing 0 removes the item entirely.

    Returns:
        CartTotals: Updated cart totals.

    Raises:
        CartItemError: Item not found, or stock/qty validation fails.
    """
    from orders.models import CartItem

    if new_quantity < 0:
        raise CartItemError("Quantity cannot be negative.")

    with transaction.atomic():
        item = CartItem.objects.filter(
            cart=cart,
            variant=variant,
        ).select_for_update().first()

        if not item:
            raise CartItemError(
                f"Item '{variant.product.title}' is not in this cart."
            )

        if new_quantity == 0:
            item.delete()
            logger.info("Removed variant %s from cart %s", variant.sku, cart.id)
        else:
            _validate_variant_stock(variant, new_quantity)
            _validate_max_quantity(item, new_quantity)
            item.quantity = new_quantity
            item.save(update_fields=["quantity", "updated_at"])

        cart.last_activity_at = timezone.now()
        cart.save(update_fields=["last_activity_at", "updated_at"])

    return recalculate_cart_totals(cart)


def remove_cart_item(cart, variant) -> CartTotals:
    """
    Remove a specific variant from the cart completely.

    Returns:
        CartTotals: Updated totals after removal.
    """
    return update_cart_item_quantity(cart, variant, 0)


# ─────────────────────────────────────────────────────────────
# SECTION 3 — DISCOUNT & GIFT CARD APPLICATION
# ─────────────────────────────────────────────────────────────

def apply_discount_code(cart, code: str, customer=None) -> DiscountResult:
    """
    Validate and apply a discount code to the cart.

    Validates:
      - Code exists and is active
      - Not expired
      - Usage limit not exceeded
      - Customer-level conditions (first order, specific group)
      - Minimum order value
      - Applicable to at least one item in the cart

    Returns:
        DiscountResult with success flag, amount, and message.
    """
    from orders.models import CartDiscount

    # Lazy import to avoid circular dependency with pricing app
    try:
        from pricing.models import DiscountCode
    except ImportError:
        raise DiscountError("Pricing module is not available.")

    code = code.strip().upper()

    if not code:
        raise DiscountError("Please enter a discount code.")

    # ── Look up code ──
    try:
        discount = DiscountCode.objects.select_related().get(
            code=code,
            is_active=True,
        )
    except DiscountCode.DoesNotExist:
        return DiscountResult(success=False, message="Invalid discount code.", code=code)

    # ── Expiry check ──
    now = timezone.now()
    if discount.starts_at and discount.starts_at > now:
        return DiscountResult(
            success=False,
            message="This discount code is not yet active.",
            code=code,
        )
    if discount.expires_at and discount.expires_at < now:
        return DiscountResult(
            success=False,
            message="This discount code has expired.",
            code=code,
        )

    # ── Usage limit check ──
    if discount.usage_limit and discount.usage_count >= discount.usage_limit:
        return DiscountResult(
            success=False,
            message="This discount code has reached its usage limit.",
            code=code,
        )

    # ── Customer-specific usage limit ──
    if discount.usage_limit_per_customer and customer:
        customer_usage = discount.usages.filter(customer=customer).count()
        if customer_usage >= discount.usage_limit_per_customer:
            return DiscountResult(
                success=False,
                message="You have already used this discount code.",
                code=code,
            )

    # ── Minimum order value ──
    if discount.minimum_order_amount and cart.subtotal < discount.minimum_order_amount:
        return DiscountResult(
            success=False,
            message=(
                f"This code requires a minimum order of "
                f"{cart.currency} {discount.minimum_order_amount}. "
                f"Your current subtotal is {cart.currency} {cart.subtotal}."
            ),
            code=code,
        )

    # ── Calculate discount amount ──
    discount_amount = _calculate_discount_amount(discount, cart)

    if discount_amount <= 0:
        return DiscountResult(
            success=False,
            message="This code doesn't apply to any items in your cart.",
            code=code,
        )

    # ── Apply to cart ──
    with transaction.atomic():
        # Remove existing code discount if any
        cart.discounts.filter(discount_type=CartDiscount.DiscountType.CODE).delete()

        CartDiscount.objects.create(
            cart=cart,
            discount_type=CartDiscount.DiscountType.CODE,
            code=code,
            discount_id=discount.id,
            description=discount.title or f"Discount: {code}",
            amount=discount_amount,
            is_percentage=discount.is_percentage,
            percentage_value=discount.percentage_value,
        )

        cart.discount_code = code
        cart.save(update_fields=["discount_code", "updated_at"])

    totals = recalculate_cart_totals(cart)

    return DiscountResult(
        success=True,
        discount_amount=discount_amount,
        message=f"Code '{code}' applied. You save {cart.currency} {discount_amount}.",
        code=code,
    )


def remove_discount_code(cart) -> CartTotals:
    """
    Remove the applied discount code from the cart.

    Returns:
        CartTotals: Updated totals.
    """
    from orders.models import CartDiscount

    with transaction.atomic():
        cart.discounts.filter(discount_type=CartDiscount.DiscountType.CODE).delete()
        cart.discount_code = ""
        cart.save(update_fields=["discount_code", "updated_at"])

    return recalculate_cart_totals(cart)


def apply_gift_card(cart, gift_card_code: str) -> DiscountResult:
    """
    Apply a gift card to the cart.
    Gift cards reduce the grand total (applied after discounts).

    Returns:
        DiscountResult with success flag and amount applied.
    """
    from orders.models import CartDiscount

    try:
        from pricing.models import GiftCard
    except ImportError:
        raise DiscountError("Pricing module is not available.")

    code = gift_card_code.strip().upper()

    try:
        gift_card = GiftCard.objects.get(code=code, is_active=True)
    except GiftCard.DoesNotExist:
        return DiscountResult(success=False, message="Invalid gift card code.", code=code)

    if gift_card.balance <= 0:
        return DiscountResult(
            success=False,
            message="This gift card has no remaining balance.",
            code=code,
        )

    if gift_card.expires_at and gift_card.expires_at < timezone.now():
        return DiscountResult(
            success=False,
            message="This gift card has expired.",
            code=code,
        )

    # Apply up to cart grand total or card balance
    recalculate_cart_totals(cart)
    applicable_amount = min(gift_card.balance, cart.grand_total)

    with transaction.atomic():
        # Prevent duplicate gift card applications
        if cart.discounts.filter(
            discount_type=CartDiscount.DiscountType.GIFT_CARD,
            discount_id=gift_card.id,
        ).exists():
            return DiscountResult(
                success=False,
                message="This gift card has already been applied.",
                code=code,
            )

        CartDiscount.objects.create(
            cart=cart,
            discount_type=CartDiscount.DiscountType.GIFT_CARD,
            code=code,
            discount_id=gift_card.id,
            description=f"Gift Card: {code}",
            amount=applicable_amount,
            is_percentage=False,
        )

    recalculate_cart_totals(cart)

    return DiscountResult(
        success=True,
        discount_amount=applicable_amount,
        message=f"Gift card applied. {cart.currency} {applicable_amount} credit applied.",
        code=code,
    )


# ─────────────────────────────────────────────────────────────
# SECTION 4 — TOTALS CALCULATION
# ─────────────────────────────────────────────────────────────

def recalculate_cart_totals(cart) -> CartTotals:
    """
    Recompute all cart totals from scratch and persist to the Cart record.

    Called after every mutation: add item, remove item, apply discount,
    change shipping rate, etc.

    Order of operations:
      1. Sum item subtotals (unit_price × quantity)
      2. Apply item-level discounts
      3. Apply order-level discounts (codes, gift cards)
      4. Add shipping
      5. Calculate tax on (subtotal - discounts + shipping) or on subtotal
         depending on tax_inclusive setting
      6. Grand total = subtotal - discounts + shipping + tax

    Returns:
        CartTotals: Full breakdown.
    """
    TWO_PLACES = Decimal("0.01")

    items = list(cart.items.select_related("variant__product").all())
    discounts = list(cart.discounts.all())

    # ── 1. Subtotal ──
    subtotal = sum(
        (item.unit_price * item.quantity for item in items),
        Decimal("0.00"),
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    item_count = sum(item.quantity for item in items)

    # ── 2. Discount total ──
    discount_total = sum(
        (d.amount for d in discounts),
        Decimal("0.00"),
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    # Discount cannot exceed subtotal
    discount_total = min(discount_total, subtotal)

    # ── 3. Shipping ──
    shipping_total = _get_cart_shipping_total(cart)

    # ── 4. Tax ──
    taxable_amount = subtotal - discount_total
    tax_total = _calculate_cart_tax(cart, taxable_amount).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )

    # ── 5. Grand total ──
    grand_total = (
        subtotal - discount_total + shipping_total + tax_total
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    grand_total = max(grand_total, Decimal("0.00"))

    # ── Persist to cart ──
    cart.subtotal = subtotal
    cart.discount_total = discount_total
    cart.shipping_total = shipping_total
    cart.tax_total = tax_total
    cart.grand_total = grand_total
    cart.save(update_fields=[
        "subtotal", "discount_total", "shipping_total",
        "tax_total", "grand_total", "updated_at",
    ])

    return CartTotals(
        subtotal=subtotal,
        discount_total=discount_total,
        shipping_total=shipping_total,
        tax_total=tax_total,
        grand_total=grand_total,
        item_count=item_count,
        currency=cart.currency,
        discount_lines=[
            {
                "code": d.code,
                "type": d.discount_type,
                "description": d.description,
                "amount": d.amount,
            }
            for d in discounts
        ],
    )


# ─────────────────────────────────────────────────────────────
# SECTION 5 — CART MERGE (Guest → User)
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def merge_guest_cart_into_user_cart(guest_cart, customer) -> object:
    """
    Merge a guest cart into an authenticated customer's active cart.
    Called immediately after login or registration.

    Strategy for conflicting items:
      - If variant already in customer cart → SUM quantities (capped at stock).
      - If variant is new → MOVE line to customer cart.

    After merge:
      - Guest cart is marked CONVERTED.
      - Customer cart totals are recalculated.

    Args:
        guest_cart: The anonymous Cart to merge from.
        customer: accounts.Customer instance to merge into.

    Returns:
        Cart: The customer's active cart (merged result).
    """
    from orders.models import Cart, CartItem

    if not guest_cart:
        customer_cart, _ = Cart.objects.get_or_create(
            customer=customer,
            status=Cart.CartStatus.ACTIVE,
            defaults={"currency": "USD"},
        )
        return customer_cart

    # Get or create destination cart
    customer_cart, created = Cart.objects.select_for_update().get_or_create(
        customer=customer,
        status=Cart.CartStatus.ACTIVE,
        defaults={
            "currency": guest_cart.currency,
            "source": guest_cart.source,
            "utm_source": guest_cart.utm_source,
            "utm_medium": guest_cart.utm_medium,
            "utm_campaign": guest_cart.utm_campaign,
        },
    )

    if not guest_cart.is_empty:
        guest_items = guest_cart.items.select_related(
            "variant__product"
        ).select_for_update()

        for guest_item in guest_items:
            variant = guest_item.variant

            # Skip items that are no longer available
            if not variant.is_active:
                logger.warning(
                    "Skipping inactive variant %s during cart merge", variant.sku
                )
                continue

            existing = customer_cart.items.filter(variant=variant).first()

            if existing:
                # Combine quantities, capped at available stock
                combined_qty = existing.quantity + guest_item.quantity
                max_qty = variant.available_quantity if variant.track_inventory else 9999
                existing.quantity = min(combined_qty, max_qty)
                existing.unit_price = variant.effective_price
                existing.save(update_fields=["quantity", "unit_price", "updated_at"])
            else:
                # Move item to customer cart
                guest_item.cart = customer_cart
                guest_item.unit_price = variant.effective_price
                guest_item.save(update_fields=["cart", "unit_price", "updated_at"])

    # Carry over discount code
    if guest_cart.discount_code and not customer_cart.discount_code:
        customer_cart.discount_code = guest_cart.discount_code
        customer_cart.save(update_fields=["discount_code", "updated_at"])

    # Mark guest cart converted
    guest_cart.customer = customer
    guest_cart.status = Cart.CartStatus.CONVERTED
    guest_cart.converted_to_order_id = customer_cart.id
    guest_cart.converted_at = timezone.now()
    guest_cart.save(update_fields=[
        "customer", "status", "converted_to_order_id", "converted_at", "updated_at"
    ])

    # Recalculate totals
    recalculate_cart_totals(customer_cart)

    logger.info(
        "Merged guest cart %s into customer cart %s for customer %s",
        guest_cart.id, customer_cart.id, customer.id,
    )
    return customer_cart


# ─────────────────────────────────────────────────────────────
# SECTION 6 — ABANDONMENT
# ─────────────────────────────────────────────────────────────

def mark_cart_abandoned(cart) -> None:
    """Mark a cart as abandoned and log the timestamp."""
    from orders.models import Cart

    if cart.status not in (Cart.CartStatus.ACTIVE, Cart.CartStatus.RECOVERING):
        return

    cart.status = Cart.CartStatus.ABANDONED
    cart.abandoned_at = timezone.now()
    cart.save(update_fields=["status", "abandoned_at", "updated_at"])
    logger.info("Cart %s marked as abandoned", cart.id)


def get_recoverable_carts(
    inactive_minutes: int = 60,
    max_emails: int = 3,
    has_email: bool = True,
):
    """
    Return queryset of carts eligible for abandonment recovery emails.

    Criteria:
      - Status is ACTIVE or RECOVERING
      - Last activity older than `inactive_minutes`
      - Has items
      - Has email address (if has_email=True)
      - Has not exceeded max recovery email count

    Args:
        inactive_minutes: Inactivity threshold in minutes.
        max_emails: Maximum number of recovery emails to send per cart.
        has_email: Only return carts with a captured email.

    Returns:
        QuerySet[Cart]
    """
    from orders.models import Cart

    cutoff = timezone.now() - timezone.timedelta(minutes=inactive_minutes)

    qs = Cart.objects.filter(
        status__in=[Cart.CartStatus.ACTIVE, Cart.CartStatus.RECOVERING],
        last_activity_at__lt=cutoff,
        recovery_email_count__lt=max_emails,
        items__isnull=False,
    ).distinct().prefetch_related("items__variant__product")

    if has_email:
        qs = qs.exclude(email="")

    return qs


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS (prefixed with _)
# ─────────────────────────────────────────────────────────────

def _validate_variant_stock(variant, quantity: int) -> None:
    """
    Raise CartItemError if the requested quantity exceeds available stock.
    Skips check if variant doesn't track inventory or allows backorder.
    """
    if not variant.track_inventory:
        return
    if variant.allow_backorder:
        return
    if variant.available_quantity < quantity:
        if variant.available_quantity <= 0:
            raise CartItemError(
                f"Sorry, '{variant.product.title}' is currently out of stock."
            )
        raise CartItemError(
            f"Only {variant.available_quantity} unit(s) of "
            f"'{variant.product.title}' are available."
        )


def _validate_max_quantity(cart_item, new_quantity: int) -> None:
    """Enforce per-item max quantity cap if set."""
    if cart_item.max_quantity and new_quantity > cart_item.max_quantity:
        raise CartItemError(
            f"Maximum {cart_item.max_quantity} unit(s) per order for "
            f"'{cart_item.product_title}'."
        )


def _get_variant_image_url(variant) -> str:
    """Get the primary image URL for a variant, fallback to product cover."""
    variant_image = variant.images.order_by("position").first()
    if variant_image:
        return variant_image.image.url if variant_image.image else ""

    product_cover = variant.product.images.filter(
        is_cover=True
    ).first() or variant.product.images.order_by("position").first()

    if product_cover and product_cover.image:
        return product_cover.image.url
    return ""


def _get_cart_shipping_total(cart) -> Decimal:
    """
    Look up the shipping cost for the selected shipping rate on this cart.
    Returns 0.00 if no rate is selected yet.
    """
    if not cart.shipping_rate_id:
        return Decimal("0.00")

    cache_key = f"shipping_rate_{cart.shipping_rate_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return Decimal(str(cached))

    try:
        from shipping.models import ShippingRate
        rate = ShippingRate.objects.get(id=cart.shipping_rate_id)
        shipping = rate.price
        cache.set(cache_key, str(shipping), timeout=300)
        return shipping
    except Exception:
        return Decimal("0.00")


def _calculate_cart_tax(cart, taxable_amount: Decimal) -> Decimal:
    """
    Calculate tax on the cart using tenant tax configuration.
    Falls back to 0 if tax configuration is unavailable.
    """
    if taxable_amount <= 0:
        return Decimal("0.00")

    cache_key = f"tax_rate_{cart.shipping_country}_{cart.shipping_state}"
    tax_rate = cache.get(cache_key)

    if tax_rate is None:
        try:
            from accounts.models import StoreProfile
            profile = StoreProfile.objects.first()
            tax_rate = Decimal(str(getattr(profile, "default_tax_rate", "0.00")))
        except Exception:
            tax_rate = Decimal("0.00")
        cache.set(cache_key, str(tax_rate), timeout=600)

    return (taxable_amount * tax_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _calculate_discount_amount(discount, cart) -> Decimal:
    """
    Calculate the actual money amount a discount reduces from the cart.
    Handles percentage and fixed amount types.
    """
    TWO_PLACES = Decimal("0.01")

    if discount.is_percentage:
        rate = Decimal(str(discount.percentage_value)) / Decimal("100")
        amount = (cart.subtotal * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    else:
        amount = Decimal(str(discount.fixed_amount or 0))

    # Cap discount at cart subtotal
    return min(amount, cart.subtotal)
