"""
Canonical discount evaluation and lifecycle helpers.

This module is used by the live storefront/cart flow and also keeps the
older pricing/order utility layer working through compatibility exports.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone

logger = logging.getLogger("pricing.discount")
TWO_PLACES = Decimal("0.01")


class DiscountError(Exception):
    pass


class CurrencyConversionError(DiscountError):
    pass


class DiscountValidationError(DiscountError):
    def __init__(self, message: str, code: str = "", error_type: str = "invalid"):
        super().__init__(message)
        self.code = code
        self.error_type = error_type


@dataclass
class DiscountValidationResult:
    valid: bool = False
    code: str = ""
    discount_id: str | None = None
    discount_title: str = ""
    value_type: str = ""
    discount_amount: Decimal = Decimal("0.00")
    percentage_value: Decimal | None = None
    scope: str = "order"
    message: str = ""
    error_type: str = ""
    free_item_variant_id: str | None = None
    buy_x_get_y_promotion_id: str | None = None
    allows_stacking_with_price_lists: bool = False
    allows_stacking_with_auto_discounts: bool = False
    eligible_item_ids: list[str] = field(default_factory=list)
    allocation_method: str = "across"


@dataclass
class AutoDiscountResult:
    discount_id: str = ""
    title: str = ""
    customer_facing_title: str = ""
    discount_method: str = ""
    discount_amount: Decimal = Decimal("0.00")
    percentage_value: Decimal | None = None
    scope: str = "order"
    priority: int = 0
    is_combinable_with_codes: bool = False
    allow_stacking: bool = False
    eligible_item_ids: list[str] = field(default_factory=list)


@dataclass
class DiscountApplicationResult:
    success: bool = False
    discount_amount: Decimal = Decimal("0.00")
    message: str = ""
    applied_discount_id: str | None = None
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
    discount_source: str = ""
    discount_code: str = ""


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _normalize_code(code: str | None) -> str:
    return (code or "").strip().upper()


def _get_customer_groups(customer) -> list:
    if not customer:
        return []
    if hasattr(customer, "groups"):
        try:
            return list(customer.groups.all())
        except Exception:
            return []
    return []


def _get_customer_email(customer) -> str:
    if not customer:
        return ""
    if getattr(customer, "user", None) and getattr(customer.user, "email", ""):
        return customer.user.email
    return ""


def _customer_order_queryset(customer):
    from orders.models import Order

    if not customer:
        return Order.objects.none()
    return Order.objects.filter(customer=customer).exclude(
        status=Order.OrderStatus.CANCELLED
    ).exclude(
        financial_status=Order.FinancialStatus.FAILED
    )


def _customer_order_count(customer) -> int:
    return _customer_order_queryset(customer).count()


def _customer_is_first_order(customer) -> bool:
    return _customer_order_count(customer) == 0


def _normalize_cart_items(cart_items: list | None) -> list[dict[str, Any]]:
    normalized = []
    for item in cart_items or []:
        variant = item.get("variant")
        product = item.get("product") or getattr(variant, "product", None)
        quantity = int(item.get("quantity") or 0)
        if variant is None or product is None or quantity <= 0:
            continue
        unit_price = _money(item.get("unit_price"))
        line_subtotal = _money(item.get("line_subtotal") or (unit_price * quantity))
        compare_at = item.get("compare_at_price")
        compare_at_price = _money(compare_at) if compare_at else None
        normalized.append(
            {
                "id": str(item.get("id") or getattr(item.get("cart_item"), "id", "") or getattr(variant, "id", "")),
                "variant": variant,
                "product": product,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_subtotal": line_subtotal,
                "compare_at_price": compare_at_price,
                "is_on_sale": bool(compare_at_price and compare_at_price > unit_price),
                "sku": item.get("sku") or getattr(variant, "sku", ""),
                "product_title": item.get("product_title") or getattr(product, "name", ""),
            }
        )
    return normalized


def _product_has_tag(product, tag_value: str) -> bool:
    if not tag_value:
        return False
    tags_manager = getattr(product, "tags", None)
    if tags_manager is None:
        return False
    try:
        return tags_manager.filter(
            Q(slug__iexact=tag_value) | Q(name__iexact=tag_value)
        ).exists()
    except Exception:
        return False


def _line_matches_rule(line: dict[str, Any], rule) -> bool:
    product = line["product"]
    variant = line["variant"]
    rule_type = rule.rule_type

    if rule_type == rule.RuleType.PRODUCT:
        return bool(rule.product_id and product.id == rule.product_id)
    if rule_type == rule.RuleType.VARIANT:
        return bool(rule.variant_id and variant.id == rule.variant_id)
    if rule_type == rule.RuleType.CATEGORY:
        if not rule.category_id:
            return False
        try:
            return product.categories.filter(id=rule.category_id).exists()
        except Exception:
            return False
    if rule_type == rule.RuleType.EXCLUDE_SPECIFIC_PRODUCTS:
        return bool(rule.product_id and product.id == rule.product_id)
    if rule_type == rule.RuleType.EXCLUDE_SALE_ITEMS:
        return bool(line["is_on_sale"])
    return False


def _discount_rule_checks(discount, cart_items: list[dict[str, Any]], customer, cart_subtotal: Decimal) -> tuple[bool, str, list[dict[str, Any]]]:
    from pricing.models import DiscountRule

    rules = list(discount.rules.all())
    if not rules:
        return True, "", list(cart_items)

    included_item_ids: set[str] = set()
    include_rules_present = False
    excluded_item_ids: set[str] = set()

    for rule in rules:
        if rule.rule_type in (
            DiscountRule.RuleType.PRODUCT,
            DiscountRule.RuleType.VARIANT,
            DiscountRule.RuleType.CATEGORY,
        ):
            include_rules_present = True
            matches = [line for line in cart_items if _line_matches_rule(line, rule)]
            if rule.match_condition == DiscountRule.MatchCondition.ALL and not matches:
                return False, "This code does not apply to the items currently in your cart.", []
            for line in matches:
                included_item_ids.add(line["id"])
        elif rule.rule_type == DiscountRule.RuleType.EXCLUDE_SPECIFIC_PRODUCTS:
            for line in cart_items:
                if _line_matches_rule(line, rule):
                    excluded_item_ids.add(line["id"])
        elif rule.rule_type == DiscountRule.RuleType.EXCLUDE_SALE_ITEMS:
            for line in cart_items:
                if line["is_on_sale"]:
                    excluded_item_ids.add(line["id"])
        elif rule.rule_type == DiscountRule.RuleType.CUSTOMER_GROUP:
            groups = {group.id for group in _get_customer_groups(customer)}
            if not rule.customer_group_id or rule.customer_group_id not in groups:
                return False, "This code is not available for your customer group.", []
        elif rule.rule_type == DiscountRule.RuleType.SPECIFIC_CUSTOMER:
            if not customer or customer.id != rule.customer_id:
                return False, "This code is reserved for a different customer account.", []
        elif rule.rule_type == DiscountRule.RuleType.MINIMUM_AMOUNT:
            threshold = _money(rule.amount_threshold)
            if cart_subtotal < threshold:
                return False, f"This code requires a minimum order value of {threshold}.", []
        elif rule.rule_type == DiscountRule.RuleType.MINIMUM_QUANTITY:
            total_qty = sum(line["quantity"] for line in cart_items)
            if total_qty < int(rule.quantity_threshold or 0):
                return False, f"This code requires at least {rule.quantity_threshold} item(s).", []

    eligible_items = list(cart_items)
    if include_rules_present:
        eligible_items = [line for line in cart_items if line["id"] in included_item_ids]
    if excluded_item_ids:
        eligible_items = [line for line in eligible_items if line["id"] not in excluded_item_ids]

    if discount.scope == discount.DiscountScope.SPECIFIC_ITEMS and not eligible_items:
        return False, "This code does not apply to the items currently in your cart.", []
    return True, "", eligible_items


def _check_customer_eligibility(discount, customer) -> tuple[bool, str]:
    if discount.customer_eligibility == "all":
        return True, ""
    if customer is None:
        return False, "Please sign in to use this discount."
    if discount.customer_eligibility == "individual":
        rule_customer_ids = set(
            discount.rules.filter(
                rule_type="specific_customer",
                customer__isnull=False,
            ).values_list("customer_id", flat=True)
        )
        if rule_customer_ids and customer.id not in rule_customer_ids:
            return False, "This discount is not assigned to your account."
    if discount.customer_eligibility == "group":
        group_ids = set(
            discount.rules.filter(
                rule_type="customer_group",
                customer_group__isnull=False,
            ).values_list("customer_group_id", flat=True)
        )
        customer_group_ids = {group.id for group in _get_customer_groups(customer)}
        if group_ids and not (group_ids & customer_group_ids):
            return False, "This discount is not available for your customer segment."
    return True, ""


def _convert_amount(amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
    from pricing.models import Currency, ExchangeRate

    from_code = (from_currency or "").upper() or "USD"
    to_code = (to_currency or "").upper() or "USD"
    amount = _money(amount)
    if from_code == to_code or amount <= 0:
        return amount

    currencies = {
        currency.code: currency
        for currency in Currency.objects.filter(
            code__in={from_code, to_code}
        )
    }
    base_currency = Currency.objects.filter(is_base_currency=True).first()
    if base_currency is None:
        raise CurrencyConversionError("No base currency is configured for this store.")
    if from_code not in currencies:
        raise CurrencyConversionError(f"Currency {from_code} is not configured.")
    if to_code not in currencies:
        raise CurrencyConversionError(f"Currency {to_code} is not configured.")

    def _rate(base_code: str, target_code: str) -> Decimal:
        base = currencies.get(base_code) or Currency.objects.get(code=base_code)
        target = currencies.get(target_code) or Currency.objects.get(code=target_code)
        exchange_rate = ExchangeRate.objects.filter(
            base_currency=base,
            target_currency=target,
        ).first()
        if exchange_rate is None:
            raise CurrencyConversionError(
                f"Exchange rate from {base_code} to {target_code} is not configured."
            )
        return Decimal(str(exchange_rate.effective_rate))

    base_code = base_currency.code
    if from_code == base_code:
        return _money(amount * _rate(from_code, to_code))
    if to_code == base_code:
        direct = _rate(to_code, from_code)
        return _money(amount / direct)

    to_base = _rate(base_code, from_code)
    base_amount = amount / to_base
    return _money(base_amount * _rate(base_code, to_code))


def _discount_amount_for_validation(discount, eligible_items, cart_subtotal: Decimal, shipping_total: Decimal, currency_code: str | None) -> Decimal:
    eligible_subtotal = sum((line["line_subtotal"] for line in eligible_items), Decimal("0.00"))
    eligible_subtotal = _money(eligible_subtotal if eligible_items else cart_subtotal)

    if discount.value_type == discount.ValueType.PERCENTAGE:
        amount = eligible_subtotal * (Decimal(str(discount.percentage_value or 0)) / Decimal("100"))
        amount = _money(amount)
        if discount.max_discount_amount:
            cap = discount.max_discount_amount
            if currency_code and discount.currency and discount.currency.upper() != currency_code.upper():
                cap = _convert_amount(cap, discount.currency, currency_code)
            amount = min(amount, _money(cap))
        return min(amount, eligible_subtotal)

    if discount.value_type == discount.ValueType.FIXED_AMOUNT:
        amount = _money(discount.fixed_amount)
        from_currency = discount.currency or currency_code or "USD"
        to_currency = currency_code or from_currency
        amount = _convert_amount(amount, from_currency, to_currency)
        return min(amount, eligible_subtotal)

    if discount.value_type == discount.ValueType.FREE_SHIPPING:
        return _money(shipping_total)

    return Decimal("0.00")


def _calculate_auto_discount_amount(discount, cart_subtotal: Decimal, cart_items: list[dict[str, Any]], shipping_total: Decimal, currency_code: str) -> tuple[Decimal, list[str]]:
    eligible_items = list(cart_items)
    benefits = list(discount.benefits.all())
    selected_benefit = None

    if discount.discount_method == discount.DiscountMethod.TIERED and benefits:
        matching = [
            benefit for benefit in benefits
            if benefit.tier_min_subtotal is None or cart_subtotal >= _money(benefit.tier_min_subtotal)
        ]
        matching.sort(key=lambda benefit: (_money(benefit.tier_min_subtotal or 0), benefit.tier_order), reverse=True)
        selected_benefit = matching[0] if matching else None
    elif benefits:
        selected_benefit = benefits[0]

    if selected_benefit:
        if selected_benefit.benefit_scope == selected_benefit.BenefitScope.SPECIFIC_PRODUCT and selected_benefit.product_id:
            eligible_items = [line for line in cart_items if line["product"].id == selected_benefit.product_id]
        elif selected_benefit.benefit_scope == selected_benefit.BenefitScope.CHEAPEST_ITEM and cart_items:
            eligible_items = [min(cart_items, key=lambda line: line["unit_price"])]
        elif selected_benefit.benefit_scope == selected_benefit.BenefitScope.MOST_EXPENSIVE_ITEM and cart_items:
            eligible_items = [max(cart_items, key=lambda line: line["unit_price"])]
        elif selected_benefit.benefit_scope == selected_benefit.BenefitScope.SHIPPING:
            eligible_items = []

    eligible_item_ids = [line["id"] for line in eligible_items]
    eligible_subtotal = _money(sum((line["line_subtotal"] for line in eligible_items), Decimal("0.00")))

    percentage_value = Decimal("0.00")
    fixed_amount = Decimal("0.00")

    if selected_benefit:
        percentage_value = Decimal(str(selected_benefit.percentage_value or 0))
        fixed_amount = Decimal(str(selected_benefit.fixed_amount or 0))
    else:
        percentage_value = Decimal(str(discount.percentage_value or 0))
        fixed_amount = Decimal(str(discount.fixed_amount or 0))

    if discount.discount_method == discount.DiscountMethod.PERCENTAGE or (
        discount.discount_method == discount.DiscountMethod.TIERED and percentage_value
    ):
        amount = _money(eligible_subtotal * (percentage_value / Decimal("100")))
        if discount.max_discount_amount:
            cap = _money(discount.max_discount_amount)
            amount = min(amount, cap)
        return min(amount, eligible_subtotal), eligible_item_ids

    if discount.discount_method == discount.DiscountMethod.FIXED_AMOUNT or (
        discount.discount_method == discount.DiscountMethod.TIERED and fixed_amount
    ):
        amount = _money(fixed_amount)
        return min(amount, eligible_subtotal), eligible_item_ids

    if discount.discount_method == discount.DiscountMethod.FREE_SHIPPING:
        return _money(shipping_total), []

    return Decimal("0.00"), eligible_item_ids


def _evaluate_auto_discount_conditions(discount, cart_subtotal: Decimal, customer, cart_items: list[dict[str, Any]]) -> bool:
    from pricing.models import AutomaticDiscountCondition as ADC

    conditions = list(discount.conditions.all())
    if not conditions:
        return True

    customer_groups = {group.id for group in _get_customer_groups(customer)}
    customer_tags = set(getattr(customer, "tags", []) or []) if customer else set()
    total_qty = sum(line["quantity"] for line in cart_items)
    order_count = _customer_order_count(customer) if customer else 0

    for condition in conditions:
        if condition.condition_type == ADC.ConditionType.MINIMUM_SUBTOTAL:
            if cart_subtotal < _money(condition.amount_threshold):
                return False
        elif condition.condition_type == ADC.ConditionType.MINIMUM_QUANTITY:
            if total_qty < int(condition.quantity_threshold or 0):
                return False
        elif condition.condition_type == ADC.ConditionType.CUSTOMER_GROUP:
            if not customer or condition.customer_group_id not in customer_groups:
                return False
        elif condition.condition_type == ADC.ConditionType.PRODUCT_IN_CART:
            if not any(line["product"].id == condition.product_id for line in cart_items):
                return False
        elif condition.condition_type == ADC.ConditionType.FIRST_ORDER:
            if not customer or not _customer_is_first_order(customer):
                return False
        elif condition.condition_type == ADC.ConditionType.CUSTOMER_TAG:
            if condition.string_value not in customer_tags:
                return False
        elif condition.condition_type == ADC.ConditionType.ORDER_COUNT_MIN:
            if order_count < int(condition.integer_threshold or 0):
                return False
        elif condition.condition_type == ADC.ConditionType.ORDER_COUNT_MAX:
            if order_count > int(condition.integer_threshold or 0):
                return False
        elif condition.condition_type == ADC.ConditionType.CART_HAS_ITEM_TAG:
            if not any(_product_has_tag(line["product"], condition.string_value) for line in cart_items):
                return False
        elif condition.condition_type == ADC.ConditionType.COLLECTION_IN_CART:
            return False

    return True


def validate_discount_code(
    code: str,
    cart_subtotal: Decimal,
    customer=None,
    cart_items: list | None = None,
    ip_address: str = "",
    shipping_total: Decimal = Decimal("0.00"),
    currency_code: str | None = None,
) -> DiscountValidationResult:
    from pricing.models import DiscountCode

    normalized_items = _normalize_cart_items(cart_items)
    code = _normalize_code(code)
    if not code:
        return DiscountValidationResult(
            valid=False,
            code=code,
            message="Please enter a discount code.",
            error_type="invalid",
        )

    try:
        discount = (
            DiscountCode.objects.select_related("free_item_variant", "buy_x_get_y_promotion")
            .prefetch_related("rules")
            .get(code=code)
        )
    except DiscountCode.DoesNotExist:
        return DiscountValidationResult(
            valid=False,
            code=code,
            message="This discount code is invalid.",
            error_type="invalid",
        )

    now = timezone.now()
    if not discount.is_active:
        return DiscountValidationResult(False, code, message="This discount code is no longer active.", error_type="invalid")
    if discount.starts_at and now < discount.starts_at:
        return DiscountValidationResult(False, code, message="This discount code is not active yet.", error_type="not_eligible")
    if discount.ends_at and now > discount.ends_at:
        return DiscountValidationResult(False, code, message="This discount code has expired.", error_type="expired")
    if discount.is_usage_limit_reached:
        return DiscountValidationResult(False, code, message="This discount code has reached its usage limit.", error_type="limit_reached")

    if customer and discount.usage_limit_per_customer:
        prior_uses = discount.usages.filter(
            customer=customer,
            is_reversed=False,
        ).count()
        if prior_uses >= discount.usage_limit_per_customer:
            return DiscountValidationResult(
                False,
                code,
                message="You've already used this code the maximum number of times.",
                error_type="already_used",
            )

    eligible_customer, message = _check_customer_eligibility(discount, customer)
    if not eligible_customer:
        return DiscountValidationResult(False, code, message=message, error_type="not_eligible")

    if discount.minimum_order_amount and _money(cart_subtotal) < _money(discount.minimum_order_amount):
        shortfall = _money(discount.minimum_order_amount) - _money(cart_subtotal)
        return DiscountValidationResult(
            False,
            code,
            message=f"This code requires a minimum order value of {discount.minimum_order_amount}. Add {shortfall} more to qualify.",
            error_type="minimum_not_met",
        )

    if discount.minimum_quantity:
        total_qty = sum(line["quantity"] for line in normalized_items)
        if total_qty < int(discount.minimum_quantity):
            return DiscountValidationResult(
                False,
                code,
                message=f"This code requires at least {discount.minimum_quantity} item(s) in your cart.",
                error_type="minimum_not_met",
            )

    if discount.requires_first_order and customer and not _customer_is_first_order(customer):
        return DiscountValidationResult(
            False,
            code,
            message="This code is for first-time customers only.",
            error_type="not_eligible",
        )

    rules_valid, rules_message, eligible_items = _discount_rule_checks(
        discount,
        normalized_items,
        customer,
        _money(cart_subtotal),
    )
    if not rules_valid:
        return DiscountValidationResult(False, code, message=rules_message, error_type="not_eligible")

    if discount.scope == discount.DiscountScope.SPECIFIC_ITEMS and not eligible_items:
        return DiscountValidationResult(
            False,
            code,
            message="This code does not apply to the items currently in your cart.",
            error_type="not_eligible",
        )

    try:
        discount_amount = _discount_amount_for_validation(
            discount,
            eligible_items or normalized_items,
            _money(cart_subtotal),
            _money(shipping_total),
            currency_code,
        )
    except CurrencyConversionError as exc:
        return DiscountValidationResult(
            False,
            code,
            message=str(exc),
            error_type="invalid",
        )

    if ip_address:
        fraud = check_discount_fraud_signals(discount, customer, ip_address, customer_email=_get_customer_email(customer))
        if fraud["is_suspicious"]:
            logger.warning("Suspicious discount activity for code %s: %s", code, fraud["reason"])

    return DiscountValidationResult(
        valid=True,
        code=code,
        discount_id=str(discount.id),
        discount_title=discount.title,
        value_type=discount.value_type,
        discount_amount=discount_amount,
        percentage_value=discount.percentage_value,
        scope=discount.scope,
        message=discount.description or f"Code '{code}' applied.",
        free_item_variant_id=str(discount.free_item_variant_id) if discount.free_item_variant_id else None,
        buy_x_get_y_promotion_id=str(discount.buy_x_get_y_promotion_id) if discount.buy_x_get_y_promotion_id else None,
        allows_stacking_with_price_lists=discount.is_combinable_with_price_lists,
        allows_stacking_with_auto_discounts=discount.is_combinable_with_automatic_discounts,
        eligible_item_ids=[line["id"] for line in (eligible_items or normalized_items)],
        allocation_method=discount.allocation_method,
    )


def get_applicable_automatic_discounts(
    cart_subtotal: Decimal,
    customer=None,
    cart_items: list | None = None,
    shipping_total: Decimal = Decimal("0.00"),
    currency_code: str = "USD",
) -> list[AutoDiscountResult]:
    from pricing.models import AutomaticDiscount

    normalized_items = _normalize_cart_items(cart_items)
    now = timezone.now()
    discounts = (
        AutomaticDiscount.objects.filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .prefetch_related("conditions", "benefits")
        .order_by("-priority", "created_at")
    )

    results: list[AutoDiscountResult] = []
    for discount in discounts:
        if discount.usage_limit and discount.usage_count >= discount.usage_limit:
            continue
        if customer and discount.usage_limit_per_customer:
            from orders.models import OrderDiscount

            customer_uses = OrderDiscount.objects.filter(
                discount_type="automatic",
                discount_id=discount.id,
                order__customer=customer,
            ).exclude(order__status="cancelled").count()
            if customer_uses >= discount.usage_limit_per_customer:
                continue
        if not _evaluate_auto_discount_conditions(discount, _money(cart_subtotal), customer, normalized_items):
            continue

        amount, eligible_item_ids = _calculate_auto_discount_amount(
            discount,
            _money(cart_subtotal),
            normalized_items,
            _money(shipping_total),
            currency_code,
        )
        if amount <= 0 and discount.discount_method not in (
            discount.DiscountMethod.FREE_ITEM,
            discount.DiscountMethod.BUY_X_GET_Y,
        ):
            continue
        results.append(
            AutoDiscountResult(
                discount_id=str(discount.id),
                title=discount.title,
                customer_facing_title=discount.customer_facing_title or discount.title,
                discount_method=discount.discount_method,
                discount_amount=_money(amount),
                percentage_value=discount.percentage_value,
                scope="shipping" if discount.discount_method == discount.DiscountMethod.FREE_SHIPPING else "order",
                priority=discount.priority,
                is_combinable_with_codes=discount.is_combinable_with_codes,
                allow_stacking=discount.allow_stacking,
                eligible_item_ids=eligible_item_ids,
            )
        )
    return results


def apply_automatic_discounts(
    cart_subtotal: Decimal,
    customer=None,
    cart_items: list | None = None,
    applied_code: str = "",
    shipping_total: Decimal = Decimal("0.00"),
    currency_code: str = "USD",
    code_allows_automatic: bool = True,
) -> list[AutoDiscountResult]:
    eligible = get_applicable_automatic_discounts(
        cart_subtotal,
        customer=customer,
        cart_items=cart_items,
        shipping_total=shipping_total,
        currency_code=currency_code,
    )
    if not eligible:
        return []
    if applied_code and not code_allows_automatic:
        return []
    if applied_code:
        eligible = [discount for discount in eligible if discount.is_combinable_with_codes]
        if not eligible:
            return []

    selected = [eligible[0]]
    for candidate in eligible[1:]:
        if candidate.allow_stacking and all(chosen.allow_stacking for chosen in selected):
            selected.append(candidate)
    return selected


def calculate_line_level_discounts(
    order_items: list,
    total_discount: Decimal,
    discount_code: str = "",
    allocation_method: str = "across",
) -> list[LineLevelDiscount]:
    total_discount = _money(total_discount)
    if total_discount <= 0 or not order_items:
        return []

    items = []
    for raw_item in order_items:
        item = {
            "id": str(raw_item.get("id", "")),
            "sku": raw_item.get("sku", ""),
            "product_title": raw_item.get("product_title", ""),
            "quantity": max(int(raw_item.get("quantity", 1) or 1), 1),
            "subtotal": _money(raw_item.get("subtotal") or raw_item.get("line_subtotal") or 0),
            "unit_price": _money(raw_item.get("unit_price") or 0),
        }
        items.append(item)

    if allocation_method == "one":
        winner = max(items, key=lambda item: item["unit_price"])
        allocations = []
        for item in items:
            line_discount = min(total_discount, item["subtotal"]) if item["id"] == winner["id"] else Decimal("0.00")
            allocations.append(
                LineLevelDiscount(
                    order_item_id=item["id"],
                    sku=item["sku"],
                    product_title=item["product_title"],
                    unit_discount=_money(line_discount / item["quantity"]) if line_discount else Decimal("0.00"),
                    line_discount=_money(line_discount),
                    discount_source="code" if discount_code else "automatic",
                    discount_code=discount_code,
                )
            )
        return allocations

    if allocation_method == "each":
        total_quantity = sum(item["quantity"] for item in items)
        per_unit = _money(total_discount / total_quantity) if total_quantity else Decimal("0.00")
        remaining = total_discount
        allocations = []
        for index, item in enumerate(items):
            if index == len(items) - 1:
                line_discount = remaining
            else:
                line_discount = min(item["subtotal"], _money(per_unit * item["quantity"]))
                remaining -= line_discount
            allocations.append(
                LineLevelDiscount(
                    order_item_id=item["id"],
                    sku=item["sku"],
                    product_title=item["product_title"],
                    unit_discount=_money(line_discount / item["quantity"]),
                    line_discount=_money(line_discount),
                    discount_source="code" if discount_code else "automatic",
                    discount_code=discount_code,
                )
            )
        return allocations

    total_subtotal = sum(item["subtotal"] for item in items)
    if total_subtotal <= 0:
        return []

    remaining = total_discount
    allocations = []
    for index, item in enumerate(items):
        if index == len(items) - 1:
            line_discount = remaining
        else:
            ratio = item["subtotal"] / total_subtotal
            line_discount = _money(total_discount * ratio)
            remaining -= line_discount
        line_discount = min(_money(line_discount), item["subtotal"])
        allocations.append(
            LineLevelDiscount(
                order_item_id=item["id"],
                sku=item["sku"],
                product_title=item["product_title"],
                unit_discount=_money(line_discount / item["quantity"]),
                line_discount=_money(line_discount),
                discount_source="code" if discount_code else "automatic",
                discount_code=discount_code,
            )
        )
    return allocations


def evaluate_cart_discounts(
    *,
    cart_subtotal: Decimal,
    cart_items: list | None,
    customer=None,
    code: str = "",
    shipping_total: Decimal = Decimal("0.00"),
    currency_code: str = "USD",
    ip_address: str = "",
) -> dict[str, Any]:
    normalized_items = _normalize_cart_items(cart_items)
    subtotal = _money(cart_subtotal)
    shipping_total = _money(shipping_total)
    applied_discounts: list[dict[str, Any]] = []
    aggregated_allocations: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "order_item_id": "",
            "sku": "",
            "product_title": "",
            "unit_discount": Decimal("0.00"),
            "line_discount": Decimal("0.00"),
            "sources": [],
        }
    )

    code_result = None
    code_discount_total = Decimal("0.00")
    shipping_discount_total = Decimal("0.00")

    if code:
        code_result = validate_discount_code(
            code=code,
            cart_subtotal=subtotal,
            customer=customer,
            cart_items=normalized_items,
            ip_address=ip_address,
            shipping_total=shipping_total,
            currency_code=currency_code,
        )
        if not code_result.valid:
            return {
                "valid": False,
                "message": code_result.message,
                "code_result": code_result,
                "automatic_discounts": [],
                "applied_discounts": [],
                "line_allocations": [],
                "discount_total": Decimal("0.00"),
                "shipping_discount_total": Decimal("0.00"),
            }
        if code_result.value_type == "free_shipping":
            shipping_discount_total += _money(code_result.discount_amount)
        else:
            code_discount_total += _money(code_result.discount_amount)
            eligible_lines = [
                line for line in normalized_items
                if not code_result.eligible_item_ids or line["id"] in code_result.eligible_item_ids
            ]
            for allocation in calculate_line_level_discounts(
                [
                    {
                        "id": line["id"],
                        "sku": line["sku"],
                        "product_title": line["product_title"],
                        "quantity": line["quantity"],
                        "subtotal": line["line_subtotal"],
                        "unit_price": line["unit_price"],
                    }
                    for line in eligible_lines
                ],
                code_discount_total,
                discount_code=code_result.code,
                allocation_method=code_result.allocation_method,
            ):
                bucket = aggregated_allocations[allocation.order_item_id]
                bucket["order_item_id"] = allocation.order_item_id
                bucket["sku"] = allocation.sku
                bucket["product_title"] = allocation.product_title
                bucket["unit_discount"] = _money(bucket["unit_discount"] + allocation.unit_discount)
                bucket["line_discount"] = _money(bucket["line_discount"] + allocation.line_discount)
                bucket["sources"].append(
                    {
                        "type": "code",
                        "label": code_result.code,
                        "amount": allocation.line_discount,
                        "discount_id": code_result.discount_id,
                    }
                )
        applied_discounts.append(
            {
                "discount_type": "code",
                "code": code_result.code,
                "discount_id": code_result.discount_id,
                "description": code_result.discount_title or code_result.message,
                "amount": _money(code_result.discount_amount),
                "is_percentage": code_result.value_type == "percentage",
                "percentage_value": code_result.percentage_value,
                "allocation_method": code_result.allocation_method,
            }
        )

    auto_discounts = apply_automatic_discounts(
        subtotal,
        customer=customer,
        cart_items=normalized_items,
        applied_code=code_result.code if code_result and code_result.valid else "",
        shipping_total=shipping_total,
        currency_code=currency_code,
        code_allows_automatic=bool(code_result is None or code_result.allows_stacking_with_auto_discounts),
    )

    auto_discount_total = Decimal("0.00")
    for auto_discount in auto_discounts:
        amount = _money(auto_discount.discount_amount)
        if auto_discount.scope == "shipping":
            shipping_discount_total += amount
        else:
            auto_discount_total += amount
            eligible_lines = [
                line for line in normalized_items
                if not auto_discount.eligible_item_ids or line["id"] in auto_discount.eligible_item_ids
            ]
            for allocation in calculate_line_level_discounts(
                [
                    {
                        "id": line["id"],
                        "sku": line["sku"],
                        "product_title": line["product_title"],
                        "quantity": line["quantity"],
                        "subtotal": line["line_subtotal"],
                        "unit_price": line["unit_price"],
                    }
                    for line in eligible_lines
                ],
                amount,
                allocation_method="across",
            ):
                bucket = aggregated_allocations[allocation.order_item_id]
                bucket["order_item_id"] = allocation.order_item_id
                bucket["sku"] = allocation.sku
                bucket["product_title"] = allocation.product_title
                bucket["unit_discount"] = _money(bucket["unit_discount"] + allocation.unit_discount)
                bucket["line_discount"] = _money(bucket["line_discount"] + allocation.line_discount)
                bucket["sources"].append(
                    {
                        "type": "automatic",
                        "label": auto_discount.customer_facing_title,
                        "amount": allocation.line_discount,
                        "discount_id": auto_discount.discount_id,
                    }
                )
        applied_discounts.append(
            {
                "discount_type": "automatic",
                "code": "",
                "discount_id": auto_discount.discount_id,
                "description": auto_discount.customer_facing_title,
                "amount": amount,
                "is_percentage": auto_discount.discount_method == "percentage",
                "percentage_value": auto_discount.percentage_value,
                "allocation_method": "across",
            }
        )

    merchandise_discount_total = min(subtotal, _money(code_discount_total + auto_discount_total))
    shipping_discount_total = min(shipping_total, _money(shipping_discount_total))
    return {
        "valid": True,
        "message": code_result.message if code_result else "",
        "code_result": code_result,
        "automatic_discounts": auto_discounts,
        "applied_discounts": applied_discounts,
        "line_allocations": list(aggregated_allocations.values()),
        "discount_total": _money(merchandise_discount_total),
        "shipping_discount_total": _money(shipping_discount_total),
    }


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
):
    from pricing.models import DiscountCode, DiscountUsage

    existing = DiscountUsage.objects.filter(
        discount_code_id=discount_code_id,
        order_id=order_id,
    ).first()
    if existing:
        if existing.is_reversed:
            existing.is_reversed = False
            existing.reversed_at = None
            existing.reversal_reason = ""
            existing.discount_amount = _money(discount_amount)
            existing.order_subtotal_at_use = _money(order_subtotal)
            existing.currency = currency
            existing.customer_email = customer_email or _get_customer_email(customer)
            existing.ip_address = ip_address or None
            existing.user_agent = user_agent[:1000]
            existing.save(
                update_fields=[
                    "is_reversed",
                    "reversed_at",
                    "reversal_reason",
                    "discount_amount",
                    "order_subtotal_at_use",
                    "currency",
                    "customer_email",
                    "ip_address",
                    "user_agent",
                ]
            )
            DiscountCode.objects.filter(pk=discount_code_id).update(
                usage_count=F("usage_count") + 1,
                last_used_at=timezone.now(),
            )
        return existing

    usage = DiscountUsage.objects.create(
        discount_code_id=discount_code_id,
        customer=customer,
        order_id=order_id,
        order_number=order_number,
        discount_amount=_money(discount_amount),
        order_subtotal_at_use=_money(order_subtotal),
        currency=currency,
        customer_email=customer_email or _get_customer_email(customer),
        ip_address=ip_address or None,
        user_agent=user_agent[:1000],
    )
    DiscountCode.objects.filter(pk=discount_code_id).update(
        usage_count=F("usage_count") + 1,
        last_used_at=timezone.now(),
    )
    return usage


@transaction.atomic
def reverse_discount_usage_for_order(order, reason: str = "") -> int:
    from pricing.models import DiscountCode, DiscountUsage

    usages = list(
        DiscountUsage.objects.select_related("discount_code").filter(
            order_id=order.id,
            is_reversed=False,
        )
    )
    if not usages:
        return 0

    usage_ids = [usage.id for usage in usages]
    now = timezone.now()
    DiscountUsage.objects.filter(id__in=usage_ids).update(
        is_reversed=True,
        reversed_at=now,
        reversal_reason=(reason or "")[:255],
    )

    counts_by_discount: dict[str, int] = {}
    for usage in usages:
        discount_id = str(usage.discount_code_id)
        counts_by_discount[discount_id] = counts_by_discount.get(discount_id, 0) + 1

    for discount_id, count in counts_by_discount.items():
        discount = DiscountCode.objects.filter(pk=discount_id).first()
        if not discount:
            continue
        discount.usage_count = max(0, int(discount.usage_count or 0) - count)
        discount.save(update_fields=["usage_count", "updated_at"])

    return len(usages)


def apply_discount_to_cart(cart, code: str, customer=None) -> DiscountApplicationResult:
    from orders.models import CartDiscount

    cart_items = [
        {
            "id": str(item.id),
            "variant": item.variant,
            "product": item.variant.product,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_subtotal": item.line_total,
            "compare_at_price": item.compare_at_price,
            "sku": item.sku,
            "product_title": item.product_title,
        }
        for item in cart.items.select_related("variant__product").all()
    ]
    result = validate_discount_code(
        code=code,
        cart_subtotal=_money(cart.subtotal),
        customer=customer,
        cart_items=cart_items,
        ip_address=getattr(cart, "ip_address", ""),
        shipping_total=_money(cart.shipping_total),
        currency_code=getattr(cart, "currency", "USD"),
    )
    if not result.valid:
        return DiscountApplicationResult(success=False, message=result.message)

    with transaction.atomic():
        cart.discounts.filter(discount_type=CartDiscount.DiscountType.CODE).delete()
        CartDiscount.objects.create(
            cart=cart,
            discount_type=CartDiscount.DiscountType.CODE,
            code=result.code,
            discount_id=result.discount_id,
            description=result.discount_title or result.message,
            amount=_money(result.discount_amount),
            is_percentage=result.value_type == "percentage",
            percentage_value=result.percentage_value,
        )
        cart.discount_code = result.code
        cart.save(update_fields=["discount_code", "updated_at"])

    return DiscountApplicationResult(
        success=True,
        discount_amount=_money(result.discount_amount),
        message=result.message,
        applied_discount_id=result.discount_id,
        applied_code=result.code,
        total_discount=_money(result.discount_amount),
    )


def remove_discount_from_cart(cart) -> bool:
    with transaction.atomic():
        cart.discounts.filter(discount_type="code").delete()
        cart.discount_code = ""
        cart.save(update_fields=["discount_code", "updated_at"])
    return True


def check_discount_fraud_signals(discount, customer, ip_address: str, customer_email: str = "") -> dict[str, Any]:
    from pricing.models import DiscountUsage

    signals: list[str] = []
    now = timezone.now()

    if ip_address:
        ip_uses_last_day = DiscountUsage.objects.filter(
            discount_code=discount,
            is_reversed=False,
            ip_address=ip_address,
            used_at__gte=now - timezone.timedelta(hours=24),
        ).count()
        if ip_uses_last_day >= 5:
            signals.append(f"High IP velocity: {ip_uses_last_day} redemptions in 24h")

    email = (customer_email or _get_customer_email(customer) or "").strip().lower()
    if "+" in email and "@" in email:
        base_local, domain = email.split("@", 1)
        normalized_local = base_local.split("+", 1)[0]
        same_base_recent = DiscountUsage.objects.filter(
            discount_code=discount,
            is_reversed=False,
            customer_email__iendswith=f"@{domain}",
            used_at__gte=now - timezone.timedelta(days=7),
        )
        same_base_recent = [
            usage for usage in same_base_recent
            if usage.customer_email and usage.customer_email.split("@", 1)[0].split("+", 1)[0].lower() == normalized_local
        ]
        if len(same_base_recent) >= 3:
            signals.append("Repeated plus-address email pattern detected")

    last_hour_count = DiscountUsage.objects.filter(
        discount_code=discount,
        is_reversed=False,
        used_at__gte=now - timezone.timedelta(hours=1),
    ).count()
    previous_window_count = DiscountUsage.objects.filter(
        discount_code=discount,
        is_reversed=False,
        used_at__gte=now - timezone.timedelta(hours=25),
        used_at__lt=now - timezone.timedelta(hours=1),
    ).count()
    hourly_baseline = Decimal(previous_window_count) / Decimal("24") if previous_window_count else Decimal("0")
    if last_hour_count >= 10 and (hourly_baseline == 0 or Decimal(last_hour_count) >= hourly_baseline * Decimal("4")):
        signals.append("Usage spike detected in the last hour")

    return {
        "is_suspicious": bool(signals),
        "reason": "; ".join(signals),
        "signals": signals,
    }
