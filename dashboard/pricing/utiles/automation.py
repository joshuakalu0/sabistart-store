from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from dashboard.notification.models import (
    ChannelType,
    DeliveryStatus,
    NotificationEvent,
    NotificationJob,
    NotificationLog,
)
from dashboard.pricing.models import DiscountCode, DiscountRule, IssuedDiscountCode, PricingAutomationDeliveryLog, PricingAutomationRule
from dashboard.pricing.utiles.advanced import refresh_experiment_snapshots, sync_dynamic_customer_groups
from public.cart.models import Cart, Order
from public.product.models import ProductReview
from public.userauth.models import Customer


CODE_ALPHABET = string.ascii_uppercase + string.digits


@dataclass
class PricingAutomationSummary:
    rules_seen: int = 0
    rules_run: int = 0
    issued_codes: int = 0
    queued_jobs: int = 0
    prepared_only: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "rules_seen": self.rules_seen,
            "rules_run": self.rules_run,
            "issued_codes": self.issued_codes,
            "queued_jobs": self.queued_jobs,
            "prepared_only": self.prepared_only,
            "errors": self.errors,
        }


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _channel_for_payload(*, recipient_email: str = "", customer=None) -> str:
    if recipient_email:
        return ChannelType.EMAIL
    if customer is not None:
        return ChannelType.IN_APP
    return ChannelType.EMAIL


def _promotion_subject(rule: PricingAutomationRule, discount_code: DiscountCode) -> str:
    label = discount_code.title or discount_code.code
    trigger_label = rule.get_trigger_type_display()
    return f"{trigger_label}: {label}"


def _promotion_body(rule: PricingAutomationRule, discount_code: DiscountCode, *, customer=None) -> str:
    customer_name = ""
    if customer is not None:
        customer_name = getattr(customer, "display_name", "") or ""
    opener = f"Hi {customer_name}," if customer_name else "Hello,"
    detail = discount_code.description or f"Use code {discount_code.code} on your next order."
    return f"{opener}\n\n{detail}\n\nCode: {discount_code.code}"


def _generate_unique_code(prefix: str) -> str:
    cleaned_prefix = "".join(ch for ch in (prefix or "").upper() if ch.isalnum())[:18]
    while True:
        suffix = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        code = f"{cleaned_prefix}-{suffix}" if cleaned_prefix else suffix
        if not DiscountCode.objects.filter(code=code).exists():
            return code


def _clone_discount_rules(source_discount: DiscountCode, cloned_discount: DiscountCode, *, customer=None) -> None:
    for rule in source_discount.rules.all():
        kwargs = {
            "discount_code": cloned_discount,
            "rule_type": rule.rule_type,
            "match_condition": rule.match_condition,
            "product": rule.product,
            "variant": rule.variant,
            "category": rule.category,
            "customer_group": rule.customer_group,
            "customer": customer if rule.rule_type == DiscountRule.RuleType.SPECIFIC_CUSTOMER else rule.customer,
            "amount_threshold": rule.amount_threshold,
            "quantity_threshold": rule.quantity_threshold,
        }
        if rule.rule_type == DiscountRule.RuleType.SPECIFIC_CUSTOMER and customer is None:
            continue
        DiscountRule.objects.create(**kwargs)


def _create_unique_discount_from_source(
    rule: PricingAutomationRule,
    *,
    customer=None,
    source_event_type: str,
    source_object_id=None,
) -> DiscountCode:
    source = rule.source_discount
    valid_for_hours = int((rule.config or {}).get("valid_for_hours") or 48)
    code_value = _generate_unique_code(rule.issue_prefix or source.code)
    ends_at = timezone.now() + timedelta(hours=valid_for_hours)
    discount = DiscountCode.objects.create(
        code=code_value,
        title=f"{source.title} • issued",
        description=source.description,
        value_type=source.value_type,
        percentage_value=source.percentage_value,
        fixed_amount=source.fixed_amount,
        currency=source.currency,
        free_item_variant=source.free_item_variant,
        buy_x_get_y_promotion=source.buy_x_get_y_promotion,
        scope=source.scope,
        allocation_method=source.allocation_method,
        usage_limit=1,
        usage_limit_per_customer=1,
        minimum_order_amount=source.minimum_order_amount,
        minimum_quantity=source.minimum_quantity,
        requires_first_order=source.requires_first_order,
        customer_eligibility="individual" if customer is not None else source.customer_eligibility,
        is_combinable_with_price_lists=source.is_combinable_with_price_lists,
        is_combinable_with_automatic_discounts=source.is_combinable_with_automatic_discounts,
        is_combinable_with_other_codes=source.is_combinable_with_other_codes,
        max_discount_amount=source.max_discount_amount,
        internal_note=f"Auto-issued from {source.code} via {rule.name}",
        attributed_partner=source.attributed_partner,
        total_stack_cap_amount=source.total_stack_cap_amount,
        eligible_countries=source.eligible_countries,
        eligible_states=source.eligible_states,
        eligible_cities=source.eligible_cities,
        is_active=True,
        starts_at=timezone.now(),
        ends_at=ends_at,
    )
    _clone_discount_rules(source, discount, customer=customer)
    if customer is not None:
        DiscountRule.objects.create(
            discount_code=discount,
            rule_type=DiscountRule.RuleType.SPECIFIC_CUSTOMER,
            customer=customer,
            match_condition=DiscountRule.MatchCondition.ALL,
        )
    return discount


def _customer_matches_rule(rule: PricingAutomationRule, customer) -> bool:
    if customer is None:
        return not rule.requires_verified_customer and rule.target_group_id is None
    if rule.requires_verified_customer and not getattr(getattr(customer, "user", None), "is_verified", False):
        return False
    if rule.target_group_id:
        sync_dynamic_customer_groups(customer=customer)
        if not customer.groups.filter(pk=rule.target_group_id).exists():
            return False
    return True


def _existing_delivery(rule: PricingAutomationRule, *, customer=None, cart=None, order=None, source_object_id=None):
    query = PricingAutomationDeliveryLog.objects.filter(rule=rule)
    if customer is not None:
        query = query.filter(customer=customer)
    if cart is not None:
        query = query.filter(cart_id=cart.id)
    if order is not None:
        query = query.filter(order_id=order.id)
    if source_object_id is not None:
        query = query.filter(details__source_object_id=str(source_object_id))
    return query.first()


def _create_delivery_job(
    rule: PricingAutomationRule,
    discount_code: DiscountCode,
    *,
    customer=None,
    recipient_email: str = "",
    source_event_type: str = "",
    source_object_id=None,
    payload: dict[str, Any] | None = None,
):
    payload = dict(payload or {})
    payload.setdefault("subject", _promotion_subject(rule, discount_code))
    payload.setdefault("body", _promotion_body(rule, discount_code, customer=customer))
    payload.setdefault("discount_code", discount_code.code)
    payload.setdefault("discount_code_id", str(discount_code.id))
    payload.setdefault("rule_name", rule.name)
    payload.setdefault("trigger_type", rule.trigger_type)
    payload.setdefault("source_object_id", str(source_object_id or ""))
    payload.setdefault("customer_id", str(customer.id) if customer is not None else "")

    channel_type = _channel_for_payload(recipient_email=recipient_email, customer=customer)
    recipient_name = ""
    if customer is not None:
        recipient_name = getattr(customer, "display_name", "") or ""
    return NotificationJob.objects.create(
        template=None,
        template_version=None,
        channel=None,
        channel_type=channel_type,
        customer=customer,
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        event_slug=f"pricing.automation.{rule.trigger_type}",
        event_object_type=source_event_type,
        event_object_id=source_object_id,
        context_data=payload,
        priority=NotificationJob.JobPriority.NORMAL,
        send_at=timezone.now(),
        status=NotificationJob.JobStatus.QUEUED,
        max_attempts=3,
        dedup_key="",
    )


@transaction.atomic
def issue_discount_for_rule(
    rule: PricingAutomationRule,
    *,
    customer=None,
    recipient_email: str = "",
    cart=None,
    order=None,
    review=None,
    extra_payload: dict[str, Any] | None = None,
):
    source_object_id = None
    source_event_type = ""
    if cart is not None:
        source_object_id = cart.id
        source_event_type = "cart"
    elif order is not None:
        source_object_id = order.id
        source_event_type = "order"
    elif review is not None:
        source_object_id = review.id
        source_event_type = "review"
    elif customer is not None:
        source_object_id = customer.id
        source_event_type = "customer"

    existing_log = _existing_delivery(
        rule,
        customer=customer,
        cart=cart,
        order=order,
        source_object_id=source_object_id,
    )
    if existing_log is not None:
        return None, existing_log, None

    if rule.delivery_mode == PricingAutomationRule.DeliveryMode.UNIQUE:
        discount_code = _create_unique_discount_from_source(
            rule,
            customer=customer,
            source_event_type=source_event_type,
            source_object_id=source_object_id,
        )
    else:
        discount_code = rule.source_discount

    issued_code = IssuedDiscountCode.objects.create(
        rule=rule,
        customer=customer,
        discount_code=discount_code,
        source_event_type=source_event_type,
        source_object_id=source_object_id,
        delivery_payload=dict(extra_payload or {}),
        expires_at=getattr(discount_code, "ends_at", None),
    )

    notification_job = None
    result = "prepared"
    if recipient_email or customer is not None:
        notification_job = _create_delivery_job(
            rule,
            discount_code,
            customer=customer,
            recipient_email=recipient_email,
            source_event_type=source_event_type,
            source_object_id=source_object_id,
            payload={
                **dict(extra_payload or {}),
                "issued_code_id": str(issued_code.id),
            },
        )
        result = "queued"

    delivery_log = PricingAutomationDeliveryLog.objects.create(
        rule=rule,
        issued_code=issued_code,
        customer=customer,
        cart_id=getattr(cart, "id", None),
        order_id=getattr(order, "id", None),
        order_number=getattr(order, "order_number", ""),
        notification_job_id=getattr(notification_job, "id", None),
        channel=getattr(notification_job, "channel_type", ""),
        result=result,
        details={
            "discount_code": discount_code.code,
            "source_event_type": source_event_type,
            "source_object_id": str(source_object_id or ""),
            **dict(extra_payload or {}),
        },
    )

    PricingAutomationRule.objects.filter(pk=rule.pk).update(
        issued_count=F("issued_count") + 1,
    )
    rule.issued_count = int(rule.issued_count or 0) + 1
    return issued_code, delivery_log, notification_job


def _run_abandoned_cart_rule(rule: PricingAutomationRule, *, now, summary: PricingAutomationSummary) -> None:
    cutoff = now - timedelta(minutes=max(int(rule.delay_minutes or 0), 60))
    carts = (
        Cart.objects.select_related("customer__user")
        .filter(status__in=[Cart.CartStatus.ACTIVE, Cart.CartStatus.RECOVERING])
        .filter(converted_to_order_id__isnull=True)
        .filter(last_activity_at__lte=cutoff)
        .filter(Q(email__gt="") | Q(customer__isnull=False))
    )
    for cart in carts:
        customer = cart.customer
        if not _customer_matches_rule(rule, customer):
            continue
        recipient_email = cart.email or getattr(getattr(customer, "user", None), "email", "") or ""
        issued_code, _, job = issue_discount_for_rule(
            rule,
            customer=customer,
            recipient_email=recipient_email,
            cart=cart,
            extra_payload={"checkout_token": cart.checkout_token},
        )
        if issued_code is None:
            continue
        summary.issued_codes += 1
        if job is not None:
            summary.queued_jobs += 1
        else:
            summary.prepared_only += 1
        Cart.objects.filter(pk=cart.pk).update(
            status=Cart.CartStatus.RECOVERING,
            recovery_email_sent_at=now,
            recovery_email_count=F("recovery_email_count") + 1,
        )


def _run_post_purchase_rule(rule: PricingAutomationRule, *, now, summary: PricingAutomationSummary) -> None:
    cutoff = now - timedelta(minutes=int(rule.delay_minutes or 0))
    window_start = now - timedelta(days=max(int(rule.evaluation_window_days or 30), 1))
    orders = (
        Order.objects.select_related("customer__user")
        .filter(placed_at__gte=window_start, placed_at__lte=cutoff)
        .exclude(status="cancelled")
    )
    for order in orders:
        customer = order.customer
        if not _customer_matches_rule(rule, customer):
            continue
        issued_code, _, job = issue_discount_for_rule(
            rule,
            customer=customer,
            recipient_email=order.customer_email,
            order=order,
            extra_payload={"order_number": order.order_number},
        )
        if issued_code is None:
            continue
        summary.issued_codes += 1
        summary.queued_jobs += int(job is not None)
        summary.prepared_only += int(job is None)


def _run_win_back_rule(rule: PricingAutomationRule, *, now, summary: PricingAutomationSummary) -> None:
    inactive_days = int((rule.config or {}).get("inactive_days") or max(int(rule.evaluation_window_days or 30), 30))
    customers = (
        Customer.objects.select_related("user")
        .filter(total_orders__gt=0, last_order_at__isnull=False)
        .filter(last_order_at__lte=now - timedelta(days=inactive_days))
    )
    for customer in customers:
        if not _customer_matches_rule(rule, customer):
            continue
        recent_log = PricingAutomationDeliveryLog.objects.filter(
            rule=rule,
            customer=customer,
            created_at__gte=now - timedelta(days=inactive_days),
        ).exists()
        if recent_log:
            continue
        recipient_email = getattr(getattr(customer, "user", None), "email", "") or ""
        issued_code, _, job = issue_discount_for_rule(
            rule,
            customer=customer,
            recipient_email=recipient_email,
            extra_payload={"inactive_days": inactive_days},
        )
        if issued_code is None:
            continue
        summary.issued_codes += 1
        summary.queued_jobs += int(job is not None)
        summary.prepared_only += int(job is None)


def _run_milestone_rule(rule: PricingAutomationRule, *, now, summary: PricingAutomationSummary) -> None:
    config = dict(rule.config or {})
    min_orders = int(config.get("min_orders") or config.get("min_total_orders") or 0)
    min_spend = _money(config.get("min_total_spend"))
    customers = Customer.objects.select_related("user").filter(status=Customer.Status.ACTIVE)
    if min_orders:
        customers = customers.filter(total_orders__gte=min_orders)
    if min_spend > 0:
        customers = customers.filter(total_spent__gte=min_spend)
    for customer in customers:
        if not _customer_matches_rule(rule, customer):
            continue
        milestone_key = f"orders:{min_orders}|spend:{min_spend}"
        if PricingAutomationDeliveryLog.objects.filter(
            rule=rule,
            customer=customer,
            details__milestone_key=milestone_key,
        ).exists():
            continue
        recipient_email = getattr(getattr(customer, "user", None), "email", "") or ""
        issued_code, _, job = issue_discount_for_rule(
            rule,
            customer=customer,
            recipient_email=recipient_email,
            extra_payload={"milestone_key": milestone_key},
        )
        if issued_code is None:
            continue
        summary.issued_codes += 1
        summary.queued_jobs += int(job is not None)
        summary.prepared_only += int(job is None)


def _run_birthday_rule(rule: PricingAutomationRule, *, now, summary: PricingAutomationSummary) -> None:
    month = now.month
    day = now.day
    customers = (
        Customer.objects.select_related("user")
        .filter(user__date_of_birth__month=month, user__date_of_birth__day=day)
    )
    for customer in customers:
        if not _customer_matches_rule(rule, customer):
            continue
        if PricingAutomationDeliveryLog.objects.filter(
            rule=rule,
            customer=customer,
            created_at__date=now.date(),
        ).exists():
            continue
        recipient_email = getattr(getattr(customer, "user", None), "email", "") or ""
        issued_code, _, job = issue_discount_for_rule(
            rule,
            customer=customer,
            recipient_email=recipient_email,
            extra_payload={"birthday": now.date().isoformat()},
        )
        if issued_code is None:
            continue
        summary.issued_codes += 1
        summary.queued_jobs += int(job is not None)
        summary.prepared_only += int(job is None)


def _run_review_reward_rule(rule: PricingAutomationRule, *, now, summary: PricingAutomationSummary) -> None:
    cutoff = now - timedelta(minutes=int(rule.delay_minutes or 0))
    window_start = now - timedelta(days=max(int(rule.evaluation_window_days or 30), 1))
    reviews = (
        ProductReview.objects.select_related("customer__user", "product")
        .filter(created_at__gte=window_start, created_at__lte=cutoff)
        .exclude(status=ProductReview.Status.REJECTED)
    )
    for review in reviews:
        customer = review.customer
        if not _customer_matches_rule(rule, customer):
            continue
        recipient_email = getattr(getattr(customer, "user", None), "email", "") or ""
        issued_code, _, job = issue_discount_for_rule(
            rule,
            customer=customer,
            recipient_email=recipient_email,
            review=review,
            extra_payload={"product_slug": review.product.slug},
        )
        if issued_code is None:
            continue
        summary.issued_codes += 1
        summary.queued_jobs += int(job is not None)
        summary.prepared_only += int(job is None)


def run_pricing_automation(*, now=None) -> PricingAutomationSummary:
    now = now or timezone.now()
    summary = PricingAutomationSummary()
    sync_dynamic_customer_groups()
    refresh_experiment_snapshots()

    rules = list(
        PricingAutomationRule.objects.select_related("source_discount", "target_group")
        .filter(is_active=True)
        .order_by("name")
    )
    summary.rules_seen = len(rules)

    for rule in rules:
        summary.rules_run += 1
        if rule.trigger_type == PricingAutomationRule.TriggerType.ABANDONED_CART:
            _run_abandoned_cart_rule(rule, now=now, summary=summary)
        elif rule.trigger_type == PricingAutomationRule.TriggerType.POST_PURCHASE:
            _run_post_purchase_rule(rule, now=now, summary=summary)
        elif rule.trigger_type == PricingAutomationRule.TriggerType.WIN_BACK:
            _run_win_back_rule(rule, now=now, summary=summary)
        elif rule.trigger_type == PricingAutomationRule.TriggerType.MILESTONE:
            _run_milestone_rule(rule, now=now, summary=summary)
        elif rule.trigger_type == PricingAutomationRule.TriggerType.BIRTHDAY:
            _run_birthday_rule(rule, now=now, summary=summary)
        elif rule.trigger_type == PricingAutomationRule.TriggerType.REVIEW_REWARD:
            _run_review_reward_rule(rule, now=now, summary=summary)
        PricingAutomationRule.objects.filter(pk=rule.pk).update(
            run_count=F("run_count") + 1,
            last_run_at=now,
        )

    return summary


def process_due_notification_jobs(*, limit: int = 100, now=None) -> dict[str, int]:
    now = now or timezone.now()
    processed = 0
    completed = 0
    failed = 0
    queued = (
        NotificationJob.objects.select_related("customer")
        .filter(status__in=[NotificationJob.JobStatus.QUEUED, NotificationJob.JobStatus.SCHEDULED])
        .filter(Q(send_at__lte=now) | Q(next_attempt_at__lte=now))
        .order_by("priority", "send_at")[:limit]
    )

    for job in queued:
        processed += 1
        try:
            if job.expires_at and job.expires_at <= now:
                job.status = NotificationJob.JobStatus.FAILED
                job.last_error = "Notification job expired before delivery."
                job.last_attempt_at = now
                job.next_attempt_at = None
                job.save(update_fields=["status", "last_error", "last_attempt_at", "next_attempt_at", "updated_at"])
                failed += 1
                continue

            job.status = NotificationJob.JobStatus.PROCESSING
            job.worker_id = "cron"
            job.last_attempt_at = now
            job.save(update_fields=["status", "worker_id", "last_attempt_at", "updated_at"])

            context = dict(job.context_data or {})
            recipient = job.recipient_email or job.recipient_phone or context.get("recipient_email") or ""
            if job.channel_type == ChannelType.EMAIL and not recipient:
                raise ValueError("Recipient email is required for email notification jobs.")

            subject = context.get("subject", "")
            body = context.get("body", "")
            log = NotificationLog.objects.create(
                job=job,
                template=job.template,
                template_version_number=getattr(job.template_version, "version_number", None),
                channel=job.channel,
                channel_type=job.channel_type,
                customer=job.customer,
                recipient_address=recipient or f"customer:{getattr(job.customer, 'id', '')}",
                recipient_name=job.recipient_name,
                status=DeliveryStatus.DELIVERED,
                status_updated_at=now,
                rendered_subject=subject,
                rendered_body_preview=(body or "")[:500],
                event_slug=job.event_slug,
                event_object_type=job.event_object_type,
                event_object_id=job.event_object_id,
                sent_at=now,
                delivered_at=now,
                duration_ms=0,
            )
            NotificationEvent.objects.create(
                notification_log=log,
                event_type=NotificationEvent.EventType.SEND_ATTEMPTED,
                detail="Processed by cron notification runner.",
                source="cron",
            )
            NotificationEvent.objects.create(
                notification_log=log,
                event_type=NotificationEvent.EventType.SENT,
                detail="Accepted by cron-safe local delivery processor.",
                source="cron",
            )
            NotificationEvent.objects.create(
                notification_log=log,
                event_type=NotificationEvent.EventType.DELIVERED,
                detail="Marked delivered by cron-safe local delivery processor.",
                source="cron",
            )
            job.mark_completed()
            for delivery_log in PricingAutomationDeliveryLog.objects.select_related("issued_code").filter(notification_job_id=job.id):
                delivery_log.result = "delivered"
                details = dict(delivery_log.details or {})
                details["delivered_at"] = now.isoformat()
                delivery_log.details = details
                delivery_log.save(update_fields=["result", "details", "updated_at"])
                if delivery_log.issued_code_id:
                    delivery_log.issued_code.status = IssuedDiscountCode.Status.DELIVERED
                    delivery_log.issued_code.delivered_at = now
                    delivery_log.issued_code.save(update_fields=["status", "delivered_at", "updated_at"])
            completed += 1
        except Exception as exc:
            failed += 1
            job.schedule_retry(error=str(exc), delay_seconds=300)
            for delivery_log in PricingAutomationDeliveryLog.objects.filter(notification_job_id=job.id):
                details = dict(delivery_log.details or {})
                details["last_error"] = str(exc)
                delivery_log.result = "retrying" if job.status == NotificationJob.JobStatus.QUEUED else "failed"
                delivery_log.details = details
                delivery_log.save(update_fields=["result", "details", "updated_at"])

    return {
        "processed": processed,
        "completed": completed,
        "failed": failed,
    }
