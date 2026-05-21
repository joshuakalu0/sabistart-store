from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from dashboard.pricing.models import (
    AutomaticDiscount,
    BundleOffer,
    DiscountCode,
    DiscountExperiment,
    DiscountExperimentAssignment,
    PromotionCompatibilityRule,
    PromotionConflictRecord,
    PromotionLink,
    PromotionPartner,
    build_promo_qr_svg,
)

TWO_PLACES = Decimal("0.01")


def money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def normalize_location_value(value: str | None) -> str:
    return (value or "").strip().lower()


def customer_geography_matches(customer, *, countries=None, states=None, cities=None) -> bool:
    if not customer:
        return not any([countries, states, cities])
    countries = [normalize_location_value(value) for value in (countries or []) if value]
    states = [normalize_location_value(value) for value in (states or []) if value]
    cities = [normalize_location_value(value) for value in (cities or []) if value]
    if not countries and not states and not cities:
        return True

    addresses = []
    try:
        addresses = list(customer.addresses.filter(is_active=True))
    except Exception:
        addresses = []
    if not addresses:
        return False

    for address in addresses:
        country = normalize_location_value(getattr(address, "country_code", ""))
        state = normalize_location_value(getattr(address, "state", ""))
        city = normalize_location_value(getattr(address, "city", ""))
        if countries and country not in countries:
            continue
        if states and state not in states:
            continue
        if cities and city not in cities:
            continue
        return True
    return False


def evaluate_customer_group_auto_rules(customer, group) -> bool:
    rules = dict(getattr(group, "auto_rules", {}) or {})
    if not rules:
        return False
    if customer is None:
        return False

    customer_tags = {str(tag).strip().lower() for tag in (getattr(customer, "tags", []) or []) if str(tag).strip()}
    customer_tier = str(getattr(customer, "tier", "") or "").strip().lower()
    acquisition_source = str(getattr(customer, "acquisition_source", "") or "").strip().lower()
    total_orders = int(getattr(customer, "total_orders", 0) or 0)
    total_spent = money(getattr(customer, "total_spent", 0))
    average_order_value = money(getattr(customer, "average_order_value", 0))
    last_order_at = getattr(customer, "last_order_at", None)
    today = timezone.localdate()

    if rules.get("min_order_count") is not None and total_orders < int(rules["min_order_count"]):
        return False
    if rules.get("max_order_count") is not None and total_orders > int(rules["max_order_count"]):
        return False
    if rules.get("min_total_spend") is not None and total_spent < money(rules["min_total_spend"]):
        return False
    if rules.get("max_total_spend") is not None and total_spent > money(rules["max_total_spend"]):
        return False
    if rules.get("min_aov") is not None and average_order_value < money(rules["min_aov"]):
        return False
    if rules.get("max_aov") is not None and average_order_value > money(rules["max_aov"]):
        return False

    tags_any = {str(tag).strip().lower() for tag in (rules.get("tags_any") or rules.get("tags") or []) if str(tag).strip()}
    tags_all = {str(tag).strip().lower() for tag in (rules.get("tags_all") or []) if str(tag).strip()}
    if tags_any and not (customer_tags & tags_any):
        return False
    if tags_all and not tags_all.issubset(customer_tags):
        return False

    tiers = {str(value).strip().lower() for value in (rules.get("tiers") or []) if str(value).strip()}
    if tiers and customer_tier not in tiers:
        return False

    source_values = list(rules.get("acquisition_sources") or [])
    if rules.get("acquisition_source"):
        source_values.append(rules.get("acquisition_source"))
    sources = {str(value).strip().lower() for value in source_values if str(value).strip()}
    if sources and acquisition_source not in sources:
        return False

    if rules.get("days_since_last_order_min") is not None:
        if last_order_at is None:
            return False
        if (today - last_order_at.date()).days < int(rules["days_since_last_order_min"]):
            return False
    if rules.get("days_since_last_order_max") is not None:
        if last_order_at is None:
            return False
        if (today - last_order_at.date()).days > int(rules["days_since_last_order_max"]):
            return False

    birthday_month = rules.get("birthday_month")
    birthday_day = rules.get("birthday_day")
    date_of_birth = getattr(getattr(customer, "user", None), "date_of_birth", None)
    if birthday_month is not None:
        if not date_of_birth or int(getattr(date_of_birth, "month", 0)) != int(birthday_month):
            return False
    if birthday_day is not None:
        if not date_of_birth or int(getattr(date_of_birth, "day", 0)) != int(birthday_day):
            return False

    if not customer_geography_matches(
        customer,
        countries=rules.get("countries"),
        states=rules.get("states"),
        cities=rules.get("cities"),
    ):
        return False

    return True


def sync_dynamic_customer_groups(*, customer=None) -> dict[str, list[str]]:
    from public.userauth.models import Customer as CustomerModel, CustomerGroup

    customers = [customer] if customer is not None else list(
        CustomerModel.objects.select_related("user").prefetch_related("groups")
    )
    groups = list(CustomerGroup.objects.filter(group_type=CustomerGroup.GroupType.AUTOMATIC))
    applied: dict[str, list[str]] = defaultdict(list)

    for row in customers:
        for group in groups:
            should_belong = evaluate_customer_group_auto_rules(row, group)
            already_belongs = row.groups.filter(pk=group.pk).exists()
            if should_belong and not already_belongs:
                row.groups.add(group)
            elif not should_belong and already_belongs:
                row.groups.remove(group)
            if should_belong:
                applied[str(row.id)].append(str(group.id))

    for group in groups:
        group.customer_count = group.customers.count()
        group.save(update_fields=["customer_count", "updated_at"])
    return applied


def get_customer_group_ids(customer) -> set:
    if not customer:
        return set()
    sync_dynamic_customer_groups(customer=customer)
    try:
        return {group.id for group in customer.groups.all()}
    except Exception:
        return set()


def _assignment_identity(experiment: DiscountExperiment, customer=None, session_key: str = "", cart_token: str = "") -> str:
    if customer is not None and experiment.assignment_mode == DiscountExperiment.AssignmentMode.CUSTOMER_HASH:
        return f"customer:{customer.id}"
    if session_key:
        return f"session:{session_key}"
    if cart_token:
        return f"cart:{cart_token}"
    if customer is not None:
        return f"customer:{customer.id}"
    return "anonymous"


def assign_discount_experiment_variant(
    discount_code: DiscountCode,
    *,
    customer=None,
    session_key: str = "",
    cart_id=None,
    cart_token: str = "",
):
    now = timezone.now()
    experiment = (
        DiscountExperiment.objects.filter(
            source_discount=discount_code,
            status=DiscountExperiment.Status.LIVE,
            is_active=True,
        )
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .prefetch_related("variants__discount_code")
        .order_by("-starts_at", "-created_at")
        .first()
    )
    if experiment is None:
        return None, discount_code, None

    assigned_key = _assignment_identity(
        experiment,
        customer=customer,
        session_key=session_key,
        cart_token=cart_token,
    )
    existing = experiment.assignments.select_related("variant__discount_code").filter(
        assigned_key=assigned_key
    ).first()
    if existing:
        return experiment, existing.variant.discount_code, existing

    variants = [variant for variant in experiment.variants.all() if variant.is_active]
    if not variants:
        return experiment, discount_code, None

    total_weight = sum(max(int(variant.allocation_weight or 0), 1) for variant in variants) or len(variants)
    digest = hashlib.sha256(f"{experiment.id}:{assigned_key}".encode("utf-8")).hexdigest()
    ticket = int(digest[:12], 16) % total_weight
    cursor = 0
    chosen = variants[0]
    for variant in variants:
        cursor += max(int(variant.allocation_weight or 0), 1)
        if ticket < cursor:
            chosen = variant
            break

    assignment = DiscountExperimentAssignment.objects.create(
        experiment=experiment,
        variant=chosen,
        customer=customer,
        session_key=session_key,
        cart_id=cart_id,
        assigned_key=assigned_key,
    )
    return experiment, chosen.discount_code, assignment


def mark_discount_experiment_redeemed(*, discount_code: DiscountCode, order, customer=None, session_key: str = "") -> None:
    assignments = DiscountExperimentAssignment.objects.select_related("variant", "experiment").filter(
        variant__discount_code=discount_code,
        was_redeemed=False,
    )
    if customer is not None:
        assignments = assignments.filter(Q(customer=customer) | Q(session_key=session_key))
    elif session_key:
        assignments = assignments.filter(session_key=session_key)
    assignment = assignments.order_by("-assigned_at").first()
    if assignment is None:
        return
    assignment.was_redeemed = True
    assignment.redeemed_at = timezone.now()
    assignment.order_id = order.id
    assignment.order_number = getattr(order, "order_number", "")
    assignment.revenue_attributed = money(getattr(order, "total_price", 0))
    assignment.save(update_fields=["was_redeemed", "redeemed_at", "order_id", "order_number", "revenue_attributed", "updated_at"])


def refresh_experiment_snapshots() -> int:
    from dashboard.pricing.models import DiscountExperimentSnapshot

    count = 0
    for experiment in DiscountExperiment.objects.prefetch_related("variants", "assignments"):
        winner_variant = None
        winner_rate = Decimal("-1")
        for variant in experiment.variants.all():
            assignments = experiment.assignments.filter(variant=variant)
            total = assignments.count()
            redeemed = assignments.filter(was_redeemed=True).count()
            revenue = money(
                assignments.filter(was_redeemed=True).aggregate(
                    total=models.Sum("revenue_attributed")
                )["total"]
            )
            conversion = Decimal("0.0000")
            aov = Decimal("0.00")
            if total:
                conversion = (Decimal(redeemed) / Decimal(total)).quantize(Decimal("0.0001"))
            if redeemed:
                aov = (revenue / Decimal(redeemed)).quantize(TWO_PLACES)
            snapshot = DiscountExperimentSnapshot.objects.create(
                experiment=experiment,
                variant=variant,
                assignments=total,
                redemptions=redeemed,
                conversion_rate=conversion,
                revenue_attributed=revenue,
                average_order_value=aov,
                is_winner=False,
            )
            if total >= experiment.minimum_sample_size and conversion > winner_rate:
                winner_rate = conversion
                winner_variant = variant
            count += 1
        if winner_variant is not None:
            DiscountExperimentSnapshot.objects.filter(
                experiment=experiment,
                variant=winner_variant,
                id=experiment.snapshots.filter(variant=winner_variant).order_by("-created_at").values_list("id", flat=True).first(),
            ).update(is_winner=True)
    return count


def build_promotion_link(
    *,
    discount_code: DiscountCode | None = None,
    partner: PromotionPartner | None = None,
    bundle: BundleOffer | None = None,
    landing_path: str = "",
    utm_source: str = "",
    utm_medium: str = "",
    utm_campaign: str = "",
    utm_content: str = "",
    query_overrides: dict[str, Any] | None = None,
) -> PromotionLink:
    if discount_code is None and partner is None and bundle is None:
        raise ValueError("A discount, partner, or bundle target is required.")
    target_type = PromotionLink.LinkTarget.DISCOUNT_CODE
    if partner is not None and discount_code is None:
        target_type = PromotionLink.LinkTarget.PARTNER
    if bundle is not None:
        target_type = PromotionLink.LinkTarget.BUNDLE
    link, _ = PromotionLink.objects.get_or_create(
        discount_code=discount_code,
        partner=partner,
        bundle_offer_id=getattr(bundle, "id", None),
        defaults={
            "target_type": target_type,
            "landing_path": landing_path or (
                "/promotions/coupons/" if discount_code else "/promotions/referrals/join/" if partner else f"/bundles/{bundle.slug}/"
            ),
            "utm_source": utm_source or getattr(partner, "default_utm_source", ""),
            "utm_medium": utm_medium or getattr(partner, "default_utm_medium", ""),
            "utm_campaign": utm_campaign or getattr(partner, "default_utm_campaign", ""),
            "utm_content": utm_content,
            "query_overrides": query_overrides or {},
        },
    )
    payload = f"{link.landing_path}:{discount_code.code if discount_code else ''}:{partner.slug if partner else ''}:{getattr(bundle, 'slug', '')}"
    if not link.qr_svg:
        link.qr_svg = build_promo_qr_svg(payload)
        link.save(update_fields=["qr_svg", "updated_at"])
    return link


@dataclass
class CompatibilityResolution:
    applied_discounts: list[dict[str, Any]]
    warnings: list[str]
    total_cap: Decimal | None


def _resolve_discount_object(discount_row: dict[str, Any]):
    discount_type = discount_row.get("discount_type")
    discount_id = discount_row.get("discount_id")
    if not discount_id:
        return None
    if discount_type == "code":
        return DiscountCode.objects.filter(pk=discount_id).first()
    if discount_type == "automatic":
        return AutomaticDiscount.objects.filter(pk=discount_id).first()
    return None


def _find_explicit_compatibility(left_row: dict[str, Any], right_row: dict[str, Any]):
    left_id = left_row.get("discount_id")
    right_id = right_row.get("discount_id")
    if not left_id or not right_id:
        return None
    q = Q()
    if left_row.get("discount_type") == "code":
        q &= Q(left_discount_code_id=left_id)
    else:
        q &= Q(left_automatic_discount_id=left_id)
    if right_row.get("discount_type") == "code":
        q &= Q(right_discount_code_id=right_id)
    else:
        q &= Q(right_automatic_discount_id=right_id)
    rule = PromotionCompatibilityRule.objects.filter(is_active=True).filter(q).first()
    if rule:
        return rule

    reverse_q = Q()
    if right_row.get("discount_type") == "code":
        reverse_q &= Q(left_discount_code_id=right_id)
    else:
        reverse_q &= Q(left_automatic_discount_id=right_id)
    if left_row.get("discount_type") == "code":
        reverse_q &= Q(right_discount_code_id=left_id)
    else:
        reverse_q &= Q(right_automatic_discount_id=left_id)
    return PromotionCompatibilityRule.objects.filter(is_active=True).filter(reverse_q).first()


def resolve_discount_compatibility(applied_discounts: list[dict[str, Any]]) -> CompatibilityResolution:
    if len(applied_discounts) <= 1:
        total_cap = None
        for row in applied_discounts:
            discount_obj = _resolve_discount_object(row)
            cap = money(getattr(discount_obj, "total_stack_cap_amount", None)) if discount_obj and getattr(discount_obj, "total_stack_cap_amount", None) else None
            if cap is not None:
                total_cap = cap if total_cap is None else min(total_cap, cap)
        return CompatibilityResolution(applied_discounts=applied_discounts, warnings=[], total_cap=total_cap)

    warnings: list[str] = []
    survivors = list(applied_discounts)
    denied_ids: set[str] = set()
    total_cap = None

    for row in survivors:
        discount_obj = _resolve_discount_object(row)
        cap = money(getattr(discount_obj, "total_stack_cap_amount", None)) if discount_obj and getattr(discount_obj, "total_stack_cap_amount", None) else None
        if cap is not None:
            total_cap = cap if total_cap is None else min(total_cap, cap)

    for index, left in enumerate(list(survivors)):
        if left.get("discount_id") in denied_ids:
            continue
        left_obj = _resolve_discount_object(left)
        for right in survivors[index + 1:]:
            if right.get("discount_id") in denied_ids:
                continue
            explicit = _find_explicit_compatibility(left, right)
            if explicit is not None:
                if explicit.max_combined_discount_amount:
                    cap = money(explicit.max_combined_discount_amount)
                    total_cap = cap if total_cap is None else min(total_cap, cap)
                if explicit.resolution == PromotionCompatibilityRule.Resolution.ALLOW:
                    continue
                if explicit.resolution == PromotionCompatibilityRule.Resolution.DENY:
                    denied_ids.add(str(right.get("discount_id")))
                    warnings.append(f"{left.get('description') or left.get('code')} cannot combine with {right.get('description') or right.get('code')}.")
                    continue
                if explicit.resolution == PromotionCompatibilityRule.Resolution.PREFER_LEFT:
                    denied_ids.add(str(right.get("discount_id")))
                    warnings.append(f"{left.get('description') or left.get('code')} overrides {right.get('description') or right.get('code')}.")
                    continue
                if explicit.resolution == PromotionCompatibilityRule.Resolution.PREFER_RIGHT:
                    denied_ids.add(str(left.get("discount_id")))
                    warnings.append(f"{right.get('description') or right.get('code')} overrides {left.get('description') or left.get('code')}.")
                    break

            right_obj = _resolve_discount_object(right)
            if left.get("discount_type") == "code" and right.get("discount_type") == "code":
                if not getattr(left_obj, "is_combinable_with_other_codes", False) or not getattr(right_obj, "is_combinable_with_other_codes", False):
                    denied_ids.add(str(right.get("discount_id")))
                    warnings.append(f"{left.get('code')} does not stack with {right.get('code')}.")
            elif left.get("discount_type") == "automatic" and right.get("discount_type") == "automatic":
                if not getattr(left_obj, "allow_stacking", False) or not getattr(right_obj, "allow_stacking", False):
                    loser = right if int(right_obj.priority or 0) <= int(left_obj.priority or 0) else left
                    denied_ids.add(str(loser.get("discount_id")))
                    warnings.append("Only one automatic discount can apply for this cart.")
            else:
                code_obj = left_obj if left.get("discount_type") == "code" else right_obj
                auto_obj = right_obj if left.get("discount_type") == "code" else left_obj
                if not getattr(code_obj, "is_combinable_with_automatic_discounts", False) or not getattr(auto_obj, "is_combinable_with_codes", False):
                    denied_ids.add(str(right.get("discount_id")) if right.get("discount_type") == "automatic" else str(left.get("discount_id")))
                    warnings.append("A code and the current automatic discount cannot be combined.")

    filtered = [row for row in survivors if str(row.get("discount_id")) not in denied_ids]
    return CompatibilityResolution(applied_discounts=filtered, warnings=warnings, total_cap=total_cap)


def refresh_promotion_conflicts() -> int:
    PromotionConflictRecord.objects.filter(status=PromotionConflictRecord.Status.OPEN).delete()
    created = 0

    codes = list(DiscountCode.objects.filter(is_active=True))
    autos = list(AutomaticDiscount.objects.filter(is_active=True))

    for code in codes:
        for automatic in autos:
            overlaps = True
            if code.ends_at and automatic.starts_at and code.ends_at < automatic.starts_at:
                overlaps = False
            if automatic.ends_at and code.starts_at and automatic.ends_at < code.starts_at:
                overlaps = False
            if not overlaps:
                continue
            if not code.is_combinable_with_automatic_discounts and automatic.is_combinable_with_codes:
                PromotionConflictRecord.objects.create(
                    left_type=PromotionCompatibilityRule.PromotionType.DISCOUNT_CODE,
                    left_discount_code=code,
                    right_type=PromotionCompatibilityRule.PromotionType.AUTOMATIC,
                    right_automatic_discount=automatic,
                    severity=PromotionConflictRecord.Severity.WARNING,
                    summary=f"{code.code} blocks stacking with {automatic.title}",
                    details="The coupon is active during the same period as an automatic discount but does not permit combination.",
                )
                created += 1
    return created
