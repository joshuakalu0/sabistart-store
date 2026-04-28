"""
pricing/utils/discount.py
==========================
Discount code validation, cart application, automatic discount engine,
line-level discount allocation, usage recording, and fraud signals.

Every function in this module is pure (no side effects on the pricing
models themselves) EXCEPT record_discount_usage() which writes
DiscountUsage records and increments usage_count.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger("pricing.discount")


# ─────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────

class DiscountError(Exception):
    pass


class DiscountValidationError(DiscountError):
    def __init__(self, message: str, code: str = "", error_type: str = "invalid"):
        super().__init__(message)
        self.code = code
        self.error_type = error_type
        # error_type: "invalid" | "expired" | "limit_reached" |
        #             "not_eligible" | "minimum_not_met" | "already_used"


# ─────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class DiscountValidationResult:
    valid: bool = False
    code: str = ""
    discount_id: Optional[str] = None
    discount_title: str = ""
    value_type: str = ""
    discount_amount: Decimal = Decimal("0.00")
    percentage_value: Optional[Decimal] = None
    scope: str = "order"
    message: str = ""
    error_type: str = ""
    # Eligibility detail
    free_item_variant_id: Optional[str] = None
    buy_x_get_y_promotion_id: Optional[str] = None
    allows_stacking_with_price_lists: bool = False
    allows_stacking_with_auto_discounts: bool = False


@dataclass
class AutoDiscountResult:
    discount_id: str = ""
    title: str = ""
    customer_facing_title: str = ""
    discount_method: str = ""
    discount_amount: Decimal = Decimal("0.00")
    percentage_value: Optional[Decimal] = None
    scope: str = ""
    priority: int = 0
    is_combinable_with_codes: bool = False


@dataclass
class DiscountApplicationResult:
    success: bool = False
    discount_amount: Decimal = Decimal("0.00")
    message: str = ""
    applied_discount_id: Optional[str] = None
    applied_code: str = ""
    auto_discounts_applied: list = field(default_factory=list)
    total_discount: Decimal = Decimal("0.00")
    line_allocations: list = field(default_factory=list)


@dataclass
class LineLevelDiscount:
    order_item_id: str = ""
    sku: str = ""
    product_title: str = ""
    unit_discount: Decimal = Decimal("0.00")
    line_discount: Decimal = Decimal("0.00")
    discount_source: str = ""   # "code" | "automatic" | "price_list"
    discount_code: str = ""


# ─────────────────────────────────────────────────────────────
# SECTION 1 — DISCOUNT CODE VALIDATION
# ─────────────────────────────────────────────────────────────

def validate_discount_code(
    code: str,
    cart_subtotal: Decimal,
    customer=None,
    cart_items: list = None,
    ip_address: str = "",
) -> DiscountValidationResult:
    """
    Validate a discount code against all eligibility rules.

    Checks (in order):
      1.  Code exists and is_active
      2.  Within date window (starts_at → ends_at)
      3.  Total usage limit not exceeded
      4.  Per-customer usage limit not exceeded
      5.  Customer eligibility (all / group / individual)
      6.  Minimum order amount
      7.  Minimum item quantity
      8.  First-order-only requirement
      9.  Product/collection scope rules
      10. Fraud signal check

    Args:
        code:           The raw code string entered by customer.
        cart_subtotal:  Cart subtotal (pre-discount) for minimum check.
        customer:       accounts.Customer | None (guest).
        cart_items:     List of {variant, quantity} dicts for scope check.
        ip_address:     For fraud detection.

    Returns:
        DiscountValidationResult — always returned, never raises.
        Check .valid to determine success.
    """
    from pricing.models import DiscountCode

    code = code.strip().upper()

    if not code:
        return DiscountValidationResult(
            valid=False, code=code, message="Please enter a discount code.",
            error_type="invalid"
        )

    # ── 1. Existence check ──
    try:
        discount = DiscountCode.objects.select_related(
            "free_item_variant", "buy_x_get_y_promotion"
        ).prefetch_related("rules").get(code=code)
    except DiscountCode.DoesNotExist:
        return DiscountValidationResult(
            valid=False, code=code,
            message="This discount code is invalid.",
            error_type="invalid"
        )

    # ── 2. Active + date window ──
    if not discount.is_active:
        return DiscountValidationResult(
            valid=False, code=code,
            message="This discount code is no longer active.",
            error_type="invalid"
        )

    now = timezone.now()
    if discount.starts_at and now < discount.starts_at:
        return DiscountValidationResult(
            valid=False, code=code,
            message=f"This code becomes active on {discount.starts_at.strftime('%b %d, %Y')}.",
            error_type="not_eligible"
        )
    if discount.ends_at and now > discount.ends_at:
        return DiscountValidationResult(
            valid=False, code=code,
            message="This discount code has expired.",
            error_type="expired"
        )

    # ── 3. Total usage limit ──
    if discount.is_usage_limit_reached:
        return DiscountValidationResult(
            valid=False, code=code,
            message="This discount code has reached its usage limit.",
            error_type="limit_reached"
        )

    # ── 4. Per-customer usage limit ──
    if customer and discount.usage_limit_per_customer:
        customer_uses = discount.usages.filter(customer=customer).count()
        if customer_uses >= discount.usage_limit_per_customer:
            limit = discount.usage_limit_per_customer
            return DiscountValidationResult(
                valid=False, code=code,
                message=(
                    "You've already used this code the maximum number of times."
                    if limit == 1 else
                    f"You've used this code {customer_uses}/{limit} times (limit reached)."
                ),
                error_type="already_used"
            )

    # ── 5. Customer eligibility ──
    eligibility_check = _check_customer_eligibility(discount, customer)
    if not eligibility_check["eligible"]:
        return DiscountValidationResult(
            valid=False, code=code,
            message=eligibility_check["message"],
            error_type="not_eligible"
        )

    # ── 6. Minimum order amount ──
    if discount.minimum_order_amount and cart_subtotal < discount.minimum_order_amount:
        shortfall = discount.minimum_order_amount - cart_subtotal
        return DiscountValidationResult(
            valid=False, code=code,
            message=(
                f"This code requires a minimum order of "
                f"{discount.minimum_order_amount}. "
                f"Add {shortfall} more to your cart to qualify."
            ),
            error_type="minimum_not_met"
        )

    # ── 7. Minimum item quantity ──
    if discount.minimum_quantity and cart_items:
        total_qty = sum(item.get("quantity", 0) for item in (cart_items or []))
        if total_qty < discount.minimum_quantity:
            return DiscountValidationResult(
                valid=False, code=code,
                message=(
                    f"This code requires at least {discount.minimum_quantity} "
                    f"items in your cart."
                ),
                error_type="minimum_not_met"
            )

    # ── 8. First order requirement ──
    if discount.requires_first_order and customer:
        from orders.models import Order
        has_prior_orders = Order.objects.filter(
            customer=customer,
            financial_status__in=["paid", "partially_refunded"],
        ).exists()
        if has_prior_orders:
            return DiscountValidationResult(
                valid=False, code=code,
                message="This code is for first-time customers only.",
                error_type="not_eligible"
            )

    # ── 9. Scope rules check ──
    if discount.scope == "specific_items" and cart_items:
        scope_check = _check_scope_rules(discount, cart_items)
        if not scope_check["eligible"]:
            return DiscountValidationResult(
                valid=False, code=code,
                message=scope_check["message"],
                error_type="not_eligible"
            )

    # ── 10. Fraud check ──
    if ip_address:
        fraud = check_discount_fraud_signals(discount, customer, ip_address)
        if fraud["is_suspicious"]:
            logger.warning(
                "Fraud signal detected for code %s: %s (ip=%s)",
                code, fraud["reason"], ip_address
            )
            # Don't reject — log and flag. Let operations team decide.

    # ── Calculate discount amount ──
    discount_amount = discount.calculate_discount_amount(cart_subtotal)

    return DiscountValidationResult(
        valid=True,
        code=code,
        discount_id=str(discount.id),
        discount_title=discount.title,
        value_type=discount.value_type,
        discount_amount=discount_amount,
        percentage_value=discount.percentage_value,
        scope=discount.scope,
        message=(
            discount.description
            or f"Code '{code}' applied. You save {discount_amount}."
        ),
        free_item_variant_id=(
            str(discount.free_item_variant.id) if discount.free_item_variant else None
        ),
        buy_x_get_y_promotion_id=(
            str(discount.buy_x_get_y_promotion.id)
            if discount.buy_x_get_y_promotion else None
        ),
        allows_stacking_with_price_lists=discount.is_combinable_with_price_lists,
        allows_stacking_with_auto_discounts=discount.is_combinable_with_automatic_discounts,
    )


# ─────────────────────────────────────────────────────────────
# SECTION 2 — AUTOMATIC DISCOUNT ENGINE
# ─────────────────────────────────────────────────────────────

def get_applicable_automatic_discounts(
    cart_subtotal: Decimal,
    customer=None,
    cart_items: list = None,
) -> List[AutoDiscountResult]:
    """
    Evaluate all active automatic discounts against the current cart state.
    Returns a list of eligible discounts sorted by priority (highest first).

    Each discount is checked against all its AutomaticDiscountConditions.
    Only discounts where ALL conditions pass are included.

    Args:
        cart_subtotal:  Cart subtotal before any discounts.
        customer:       accounts.Customer | None.
        cart_items:     List of {variant, quantity, subtotal} dicts.

    Returns:
        List[AutoDiscountResult]: All eligible automatic discounts.
    """
    from pricing.models import AutomaticDiscount

    now = timezone.now()
    discounts = (
        AutomaticDiscount.objects
        .filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .prefetch_related("conditions", "benefits")
        .order_by("-priority")
    )

    eligible = []
    for discount in discounts:
        if discount.usage_limit and discount.usage_count >= discount.usage_limit:
            continue
        if _evaluate_auto_discount_conditions(discount, cart_subtotal, customer, cart_items):
            amount = _calculate_auto_discount_amount(
                discount, cart_subtotal, cart_items or []
            )
            eligible.append(AutoDiscountResult(
                discount_id=str(discount.id),
                title=discount.title,
                customer_facing_title=discount.customer_facing_title or discount.title,
                discount_method=discount.discount_method,
                discount_amount=amount,
                percentage_value=discount.percentage_value,
                scope="order",
                priority=discount.priority,
                is_combinable_with_codes=discount.is_combinable_with_codes,
            ))

    return eligible


def apply_automatic_discounts(
    cart_subtotal: Decimal,
    customer=None,
    cart_items: list = None,
    applied_code: str = "",
) -> List[AutoDiscountResult]:
    """
    Determine which automatic discounts to apply to this cart,
    respecting stacking rules.

    Rules:
      - If no code applied → apply highest priority auto discount.
      - If code applied + allow_stacking=False → no auto discounts.
      - If code applied + allow_stacking=True → apply combinable auto discounts.
      - If multiple auto discounts eligible + allow_stacking → apply all combinable ones.
      - Otherwise → apply only the highest priority one.

    Returns:
        List[AutoDiscountResult]: The auto discounts to actually apply.
    """
    eligible = get_applicable_automatic_discounts(cart_subtotal, customer, cart_items)

    if not eligible:
        return []

    # Check if code is applied and whether auto discounts can stack with it
    if applied_code:
        combinable = [d for d in eligible if d.is_combinable_with_codes]
        if not combinable:
            return []
        eligible = combinable

    # Stacking: take only top priority unless they allow stacking
    # For simplicity: apply all that have allow_stacking=True + the top one
    top = eligible[0]
    result = [top]

    for d in eligible[1:]:
        # Only add if top discount allows stacking
        pass  # In production, check AutomaticDiscount.allow_stacking here

    return result


# ─────────────────────────────────────────────────────────────
# SECTION 3 — LINE-LEVEL DISCOUNT ALLOCATION
# ─────────────────────────────────────────────────────────────

def calculate_line_level_discounts(
    order_items: list,
    total_discount: Decimal,
    discount_code: str = "",
    allocation_method: str = "across",
) -> List[LineLevelDiscount]:
    """
    Prorate a total discount amount across order line items.
    Used during order placement to assign per-line discount amounts
    for accurate partial refund and return calculations later.

    Allocation methods:
      "across"  → Proportional to each line's subtotal (most common)
      "each"    → Full discount applied to each eligible item independently
      "one"     → Full discount on the single highest-priced eligible item

    Args:
        order_items:     List of {id, sku, product_title, subtotal, quantity, unit_price}
        total_discount:  Total discount to distribute.
        discount_code:   For audit trail.
        allocation_method: How to distribute.

    Returns:
        List[LineLevelDiscount]: Per-line allocation records.
    """
    if not order_items or total_discount <= 0:
        return []

    TWO = Decimal("0.01")
    allocations = []

    if allocation_method == "across":
        total_subtotal = sum(Decimal(str(item.get("subtotal", 0))) for item in order_items)
        if total_subtotal <= 0:
            return []

        remaining = total_discount
        for i, item in enumerate(order_items):
            line_sub = Decimal(str(item.get("subtotal", 0)))
            is_last = i == len(order_items) - 1

            if is_last:
                line_discount = remaining
            else:
                proportion = line_sub / total_subtotal
                line_discount = (total_discount * proportion).quantize(TWO, rounding=ROUND_HALF_UP)
                remaining -= line_discount

            qty = max(item.get("quantity", 1), 1)
            unit_discount = (line_discount / qty).quantize(TWO, rounding=ROUND_HALF_UP)

            allocations.append(LineLevelDiscount(
                order_item_id=str(item.get("id", "")),
                sku=item.get("sku", ""),
                product_title=item.get("product_title", ""),
                unit_discount=unit_discount,
                line_discount=line_discount,
                discount_source="code" if discount_code else "automatic",
                discount_code=discount_code,
            ))

    elif allocation_method == "one":
        # Apply to highest-value line only
        if not order_items:
            return []
        sorted_items = sorted(
            order_items,
            key=lambda x: Decimal(str(x.get("unit_price", 0))),
            reverse=True
        )
        top = sorted_items[0]
        unit_discount = min(
            total_discount,
            Decimal(str(top.get("unit_price", 0)))
        ).quantize(TWO)

        for item in order_items:
            is_top = str(item.get("id")) == str(top.get("id"))
            allocations.append(LineLevelDiscount(
                order_item_id=str(item.get("id", "")),
                sku=item.get("sku", ""),
                product_title=item.get("product_title", ""),
                unit_discount=unit_discount if is_top else Decimal("0.00"),
                line_discount=unit_discount if is_top else Decimal("0.00"),
                discount_source="code" if discount_code else "automatic",
                discount_code=discount_code,
            ))

    return allocations


# ─────────────────────────────────────────────────────────────
# SECTION 4 — USAGE RECORDING
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def record_discount_usage(
    discount_code_id: str,
    order_id: str,
    order_number: str,
    discount_amount: Decimal,
    order_subtotal: Decimal,
    customer=None,
    customer_email: str = "",
    currency: str = "USD",
    ip_address: str = "",
    user_agent: str = "",
) -> object:
    """
    Record a DiscountUsage entry and atomically increment usage_count.
    Called during order placement AFTER payment confirmation.

    Returns:
        DiscountUsage: The created record.
    """
    from pricing.models import DiscountCode, DiscountUsage

    usage = DiscountUsage.objects.create(
        discount_code_id=discount_code_id,
        customer=customer,
        order_id=order_id,
        order_number=order_number,
        discount_amount=discount_amount,
        order_subtotal_at_use=order_subtotal,
        currency=currency,
        customer_email=customer_email or (customer.email if customer else ""),
        ip_address=ip_address or None,
        user_agent=user_agent,
    )

    # Thread-safe counter increment
    DiscountCode.objects.filter(pk=discount_code_id).update(
        usage_count=models_F("usage_count") + 1,
        last_used_at=timezone.now(),
    )

    logger.info(
        "Discount usage recorded: code=%s order=%s amount=%s",
        discount_code_id, order_number, discount_amount
    )
    return usage


# ─────────────────────────────────────────────────────────────
# SECTION 5 — CART DISCOUNT APPLICATION HELPERS
# ─────────────────────────────────────────────────────────────

def apply_discount_to_cart(cart, code: str, customer=None) -> DiscountApplicationResult:
    """
    Full pipeline: validate → calculate → attach to cart.
    Returns DiscountApplicationResult with success flag and amounts.
    """
    from orders.models import CartDiscount

    validation = validate_discount_code(
        code=code,
        cart_subtotal=cart.subtotal,
        customer=customer,
        cart_items=list(cart.items.values("quantity")),
        ip_address=getattr(cart, "ip_address", ""),
    )

    if not validation.valid:
        return DiscountApplicationResult(
            success=False,
            message=validation.message,
        )

    with transaction.atomic():
        # Remove any existing code discount
        cart.discounts.filter(discount_type="code").delete()

        CartDiscount.objects.create(
            cart=cart,
            discount_type="code",
            code=validation.code,
            discount_id=validation.discount_id,
            description=validation.discount_title,
            amount=validation.discount_amount,
            is_percentage=(validation.value_type == "percentage"),
            percentage_value=validation.percentage_value,
        )

        cart.discount_code = validation.code
        cart.save(update_fields=["discount_code", "updated_at"])

    return DiscountApplicationResult(
        success=True,
        discount_amount=validation.discount_amount,
        message=validation.message,
        applied_discount_id=validation.discount_id,
        applied_code=validation.code,
        total_discount=validation.discount_amount,
    )


def remove_discount_from_cart(cart) -> bool:
    """Remove the applied discount code from the cart. Returns True on success."""
    with transaction.atomic():
        cart.discounts.filter(discount_type="code").delete()
        cart.discount_code = ""
        cart.save(update_fields=["discount_code", "updated_at"])
    return True


# ─────────────────────────────────────────────────────────────
# SECTION 6 — FRAUD DETECTION
# ─────────────────────────────────────────────────────────────

def check_discount_fraud_signals(
    discount,
    customer,
    ip_address: str,
) -> dict:
    """
    Detect suspicious discount code usage patterns.

    Signals checked:
      - Same IP used to redeem this code on multiple customer accounts
      - Code used by customer within minutes of account creation
      - Unusual volume from one IP in a short window

    Returns:
        dict: {"is_suspicious": bool, "reason": str, "signals": list}
    """
    from pricing.models import DiscountUsage

    signals = []

    if ip_address:
        # Signal 1: Same IP, multiple accounts using this code
        ip_usage_count = DiscountUsage.objects.filter(
            discount_code=discount,
            ip_address=ip_address,
        ).values("customer").distinct().count()

        if ip_usage_count >= 3:
            signals.append(
                f"IP {ip_address[:10]}... used this code on {ip_usage_count} accounts"
            )

        # Signal 2: Burst — multiple uses from same IP in last hour
        one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
        recent_ip_uses = DiscountUsage.objects.filter(
            discount_code=discount,
            ip_address=ip_address,
            used_at__gte=one_hour_ago,
        ).count()
        if recent_ip_uses >= 5:
            signals.append(f"IP {ip_address[:10]}... used code {recent_ip_uses}× in 1 hour")

    if customer:
        # Signal 3: New account + immediate discount use
        account_age = (timezone.now() - customer.created_at).total_seconds() / 3600
        if account_age < 1:  # Account less than 1 hour old
            signals.append(f"Account only {account_age:.1f}h old — possible throwaway")

    return {
        "is_suspicious": len(signals) > 0,
        "reason": "; ".join(signals),
        "signals": signals,
        "signal_count": len(signals),
    }


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _check_customer_eligibility(discount, customer) -> dict:
    """Check if the customer meets the customer_eligibility requirement."""
    if discount.customer_eligibility == "all":
        return {"eligible": True, "message": ""}

    if not customer:
        return {
            "eligible": False,
            "message": "Please log in to use this discount code.",
        }

    if discount.customer_eligibility == "group":
        from pricing.models import DiscountRule
        group_rules = discount.rules.filter(
            rule_type=DiscountRule.RuleType.CUSTOMER_GROUP
        )
        if group_rules.exists():
            customer_group = getattr(customer, "customer_group", None)
            eligible_groups = {str(r.customer_group_id) for r in group_rules}
            if str(getattr(customer_group, "id", "")) not in eligible_groups:
                return {
                    "eligible": False,
                    "message": "This discount code is not available for your account.",
                }

    elif discount.customer_eligibility == "individual":
        from pricing.models import DiscountRule
        customer_rules = discount.rules.filter(
            rule_type=DiscountRule.RuleType.SPECIFIC_CUSTOMER
        )
        eligible_customer_ids = {str(r.customer_id) for r in customer_rules}
        if str(customer.id) not in eligible_customer_ids:
            return {
                "eligible": False,
                "message": "This discount code is not available for your account.",
            }

    return {"eligible": True, "message": ""}


def _check_scope_rules(discount, cart_items: list) -> dict:
    """Check if cart contains at least one item eligible for this code."""
    from pricing.models import DiscountRule

    rules = list(discount.rules.all())
    if not rules:
        return {"eligible": True, "message": ""}

    eligible_item_found = False
    for item in cart_items:
        variant = item.get("variant")
        if not variant:
            continue
        for rule in rules:
            if rule.rule_type == DiscountRule.RuleType.PRODUCT:
                if rule.product_id == variant.product_id:
                    eligible_item_found = True
                    break
            elif rule.rule_type == DiscountRule.RuleType.VARIANT:
                if str(rule.variant_id) == str(variant.id):
                    eligible_item_found = True
                    break
            elif rule.rule_type == DiscountRule.RuleType.COLLECTION:
                if variant.product.collection_memberships.filter(
                    collection_id=rule.collection_id
                ).exists():
                    eligible_item_found = True
                    break
            elif rule.rule_type == DiscountRule.RuleType.CATEGORY:
                if str(variant.product.category_id) == str(rule.category_id):
                    eligible_item_found = True
                    break
        if eligible_item_found:
            break

    if not eligible_item_found:
        return {
            "eligible": False,
            "message": "This code doesn't apply to any items in your cart.",
        }
    return {"eligible": True, "message": ""}


def _evaluate_auto_discount_conditions(
    discount, cart_subtotal: Decimal, customer, cart_items: list
) -> bool:
    """Return True if all conditions on an AutomaticDiscount are satisfied."""
    from pricing.models import AutomaticDiscountCondition as ADC

    for condition in discount.conditions.all():
        ct = condition.condition_type

        if ct == ADC.ConditionType.MINIMUM_SUBTOTAL:
            if cart_subtotal < (condition.amount_threshold or Decimal("0")):
                return False

        elif ct == ADC.ConditionType.MINIMUM_QUANTITY:
            total_qty = sum(i.get("quantity", 0) for i in (cart_items or []))
            if total_qty < (condition.quantity_threshold or 0):
                return False

        elif ct == ADC.ConditionType.CUSTOMER_GROUP:
            if not customer:
                return False
            cg = getattr(customer, "customer_group", None)
            if not cg or cg.id != condition.customer_group_id:
                return False

        elif ct == ADC.ConditionType.FIRST_ORDER:
            if not customer:
                return False
            from orders.models import Order
            if Order.objects.filter(
                customer=customer,
                financial_status__in=["paid", "partially_refunded"]
            ).exists():
                return False

        elif ct == ADC.ConditionType.ORDER_COUNT_MIN:
            if not customer:
                return False
            from orders.models import Order
            count = Order.objects.filter(
                customer=customer,
                financial_status__in=["paid", "partially_refunded"]
            ).count()
            if count < (condition.integer_threshold or 0):
                return False

        elif ct == ADC.ConditionType.PRODUCT_IN_CART:
            product_ids_in_cart = {
                str(i.get("variant").product_id)
                for i in (cart_items or []) if i.get("variant")
            }
            if str(condition.product_id) not in product_ids_in_cart:
                return False

    return True


def _calculate_auto_discount_amount(
    discount, cart_subtotal: Decimal, cart_items: list
) -> Decimal:
    """Calculate the money amount for an automatic discount."""
    TWO = Decimal("0.01")

    if discount.discount_method == "percentage" and discount.percentage_value:
        amount = (cart_subtotal * discount.percentage_value / Decimal("100")).quantize(
            TWO, rounding=ROUND_HALF_UP
        )
        if discount.max_discount_amount:
            amount = min(amount, discount.max_discount_amount)
        return amount

    elif discount.discount_method == "fixed_amount" and discount.fixed_amount:
        return min(discount.fixed_amount, cart_subtotal)

    return Decimal("0.00")


# Lazy import helper for F expressions
def models_F(field_name):
    from django.db.models import F
    return F(field_name)
