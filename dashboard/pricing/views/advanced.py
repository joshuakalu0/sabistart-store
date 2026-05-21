from __future__ import annotations

import csv
import json
from decimal import Decimal
from io import StringIO
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import require_feature
from dashboard.pricing.forms import (
    BundleOfferForm,
    BundleOfferItemForm,
    DiscountExperimentForm,
    DiscountExperimentVariantForm,
    DiscountImportMappingForm,
    DiscountImportUploadForm,
    PartnerDiscountGenerationForm,
    PricingAutomationRuleForm,
    PricingSegmentForm,
    PromotionLinkForm,
    ProductReviewModerationForm,
    PromotionCompatibilityRuleForm,
    PromotionPartnerForm,
)
from dashboard.pricing.models import (
    AutomaticDiscount,
    BundleOffer,
    BundleOfferItem,
    BundleOrderLedger,
    DiscountCode,
    DiscountExperiment,
    DiscountExperimentSnapshot,
    DiscountExperimentVariant,
    DiscountImportBatch,
    DiscountImportRow,
    DiscountRule,
    IssuedDiscountCode,
    PricingAutomationDeliveryLog,
    PricingAutomationRule,
    PromotionCommissionLedger,
    PromotionCompatibilityRule,
    PromotionConflictRecord,
    PromotionLink,
    PromotionPartner,
    build_promo_qr_svg,
)
from dashboard.pricing.utiles.advanced import (
    build_promotion_link,
    refresh_experiment_snapshots,
    refresh_promotion_conflicts,
    sync_dynamic_customer_groups,
)
from dashboard.pricing.utiles.automation import (
    process_due_notification_jobs,
    run_pricing_automation,
)
from dashboard.sidebar_utiles import main_sidebar
from public.product.models import ProductReview
from public.product.review_services import refresh_product_review_stats
from public.userauth.models import CustomerGroup


def _ctx(prefix, page_title, active_menu="pricing_discounts", **extra):
    base = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix),
    }
    base.update(extra)
    return base


def _paginate(request: HttpRequest, items, *, per_page: int = 20):
    paginator = Paginator(items, per_page)
    return paginator.get_page(request.GET.get("page"))


def _post_action(label: str, url: str, tone: str = "slate"):
    return {"label": label, "url": url, "method": "post", "tone": tone}


def _link_action(label: str, url: str, tone: str = "slate"):
    return {"label": label, "url": url, "method": "get", "tone": tone}


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _fmt_money(value) -> str:
    return f"{_money(value):,.2f}"


def _fmt_datetime(value) -> str:
    if not value:
        return "—"
    return timezone.localtime(value).strftime("%b %d, %Y %H:%M")


def _promotion_link_target(link: PromotionLink):
    if link.discount_code_id:
        return link.discount_code
    if link.partner_id and link.target_type == PromotionLink.LinkTarget.PARTNER:
        return link.partner
    if link.bundle_offer_id:
        return BundleOffer.objects.filter(pk=link.bundle_offer_id).first()
    return None


def _promotion_link_target_label(link: PromotionLink) -> str:
    target = _promotion_link_target(link)
    if target is None:
        return "â€”"
    if isinstance(target, DiscountCode):
        return target.code
    if isinstance(target, PromotionPartner):
        return target.name
    if isinstance(target, BundleOffer):
        return target.name
    return str(target)


def _promotion_link_query(link: PromotionLink) -> dict[str, str]:
    query = dict(link.query_overrides or {})
    if link.discount_code_id:
        query.setdefault("discount", link.discount_code.code)
    if link.partner_id:
        query.setdefault("ref", link.partner.referral_slug or link.partner.slug)
    query.setdefault("l", link.slug)
    if link.utm_source:
        query.setdefault("utm_source", link.utm_source)
    if link.utm_medium:
        query.setdefault("utm_medium", link.utm_medium)
    if link.utm_campaign:
        query.setdefault("utm_campaign", link.utm_campaign)
    if link.utm_content:
        query.setdefault("utm_content", link.utm_content)
    return {key: str(value) for key, value in query.items() if value not in (None, "")}


def _promotion_link_share_url(request: HttpRequest, link: PromotionLink) -> str:
    base_path = link.landing_path or "/"
    query = _promotion_link_query(link)
    relative = base_path if not query else f"{base_path}?{urlencode(query)}"
    return request.build_absolute_uri(relative)


def _refresh_link_qr(link: PromotionLink, *, request: HttpRequest | None = None) -> PromotionLink:
    payload = _promotion_link_share_url(request, link) if request is not None else (
        f"{link.landing_path}:{json.dumps(_promotion_link_query(link), sort_keys=True)}"
    )
    link.qr_svg = build_promo_qr_svg(payload)
    link.save(update_fields=["qr_svg", "updated_at"])
    return link


def _copy_discount_rules(source: DiscountCode, target: DiscountCode) -> None:
    for rule in source.rules.all():
        DiscountRule.objects.create(
            discount_code=target,
            rule_type=rule.rule_type,
            match_condition=rule.match_condition,
            product=rule.product,
            variant=rule.variant,
            category=rule.category,
            customer_group=rule.customer_group,
            customer=rule.customer,
            amount_threshold=rule.amount_threshold,
            quantity_threshold=rule.quantity_threshold,
        )


def _clone_discount_code(source: DiscountCode, *, code: str, title: str, partner: PromotionPartner | None = None) -> DiscountCode:
    clone = DiscountCode.objects.create(
        code=code.strip().upper(),
        title=title,
        description=source.description,
        value_type=source.value_type,
        percentage_value=source.percentage_value,
        fixed_amount=source.fixed_amount,
        currency=source.currency,
        free_item_variant=source.free_item_variant,
        buy_x_get_y_promotion=source.buy_x_get_y_promotion,
        scope=source.scope,
        allocation_method=source.allocation_method,
        usage_limit=source.usage_limit,
        usage_limit_per_customer=source.usage_limit_per_customer,
        minimum_order_amount=source.minimum_order_amount,
        minimum_quantity=source.minimum_quantity,
        requires_first_order=source.requires_first_order,
        customer_eligibility=source.customer_eligibility,
        is_combinable_with_price_lists=source.is_combinable_with_price_lists,
        is_combinable_with_automatic_discounts=source.is_combinable_with_automatic_discounts,
        is_combinable_with_other_codes=source.is_combinable_with_other_codes,
        max_discount_amount=source.max_discount_amount,
        internal_note=source.internal_note,
        starts_at=source.starts_at,
        ends_at=source.ends_at,
        is_active=source.is_active,
        attributed_partner=partner or source.attributed_partner,
        total_stack_cap_amount=source.total_stack_cap_amount,
        eligible_countries=source.eligible_countries,
        eligible_states=source.eligible_states,
        eligible_cities=source.eligible_cities,
    )
    _copy_discount_rules(source, clone)
    return clone


def _guess_mapping(headers: list[str]) -> dict[str, str]:
    normalized = {header.lower().strip(): header for header in headers}
    guesses = {
        "code": ["code", "coupon", "discount_code"],
        "title": ["title", "name", "internal_name"],
        "description": ["description", "details"],
        "value_type": ["value_type", "type", "discount_type"],
        "percentage_value": ["percentage_value", "percentage", "percent", "percent_off"],
        "fixed_amount": ["fixed_amount", "amount", "value", "amount_off"],
        "currency": ["currency", "currency_code"],
        "scope": ["scope", "discount_scope"],
        "usage_limit": ["usage_limit", "max_uses", "total_uses"],
        "usage_limit_per_customer": ["usage_limit_per_customer", "per_customer_limit"],
        "minimum_order_amount": ["minimum_order_amount", "min_order_amount", "minimum_spend"],
        "minimum_quantity": ["minimum_quantity", "min_qty"],
        "is_active": ["is_active", "active", "enabled"],
        "starts_at": ["starts_at", "start_at", "start_date"],
        "ends_at": ["ends_at", "end_at", "end_date", "expires_at"],
        "partner_slug": ["partner_slug", "partner", "influencer", "creator_slug"],
    }
    mapping: dict[str, str] = {}
    for canonical, options in guesses.items():
        for option in options:
            if option in normalized:
                mapping[canonical] = normalized[option]
                break
    return mapping


def _parse_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "active"}


def _parse_int(value):
    if value in (None, ""):
        return None
    return int(str(value).strip())


def _parse_decimal(value):
    if value in (None, ""):
        return None
    return Decimal(str(value).strip())


def _parse_datetime(value):
    if value in (None, ""):
        return None
    raw = str(value).strip()
    try:
        parsed = timezone.datetime.fromisoformat(raw)
    except ValueError:
        parsed = timezone.datetime.strptime(raw, "%Y-%m-%d")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _normalize_row(row: dict[str, str], mapping: dict[str, str], defaults: dict[str, str]) -> tuple[dict, list[str]]:
    data: dict[str, object] = {}
    errors: list[str] = []

    def value_for(name: str, default: str = ""):
        header = mapping.get(name)
        raw = row.get(header, "") if header else ""
        return raw if raw not in (None, "") else defaults.get(name, default)

    code = str(value_for("code")).strip().upper()
    if not code:
        errors.append("Missing code.")
    data["code"] = code

    title = str(value_for("title", code or "Imported Discount")).strip()
    data["title"] = title or code
    data["description"] = str(value_for("description")).strip()

    value_type = str(value_for("value_type", defaults.get("value_type", DiscountCode.ValueType.PERCENTAGE))).strip().lower()
    allowed_value_types = {choice[0] for choice in DiscountCode.ValueType.choices}
    if value_type not in allowed_value_types:
        errors.append(f"Unsupported value type '{value_type}'.")
    data["value_type"] = value_type

    percentage_value = value_for("percentage_value")
    fixed_amount = value_for("fixed_amount")
    if value_type == DiscountCode.ValueType.PERCENTAGE:
        try:
            data["percentage_value"] = _parse_decimal(percentage_value)
            if data["percentage_value"] is None:
                errors.append("Percentage discounts require a percentage_value.")
        except Exception:
            errors.append("Invalid percentage_value.")
    elif value_type == DiscountCode.ValueType.FIXED_AMOUNT:
        try:
            data["fixed_amount"] = _parse_decimal(fixed_amount)
            if data["fixed_amount"] is None:
                errors.append("Fixed amount discounts require a fixed_amount.")
        except Exception:
            errors.append("Invalid fixed_amount.")

    data["currency"] = str(value_for("currency", defaults.get("currency", "USD"))).strip().upper() or "USD"
    scope = str(value_for("scope", defaults.get("scope", DiscountCode.DiscountScope.ORDER))).strip().lower()
    allowed_scopes = {choice[0] for choice in DiscountCode.DiscountScope.choices}
    if scope not in allowed_scopes:
        errors.append(f"Unsupported scope '{scope}'.")
    data["scope"] = scope or DiscountCode.DiscountScope.ORDER

    try:
        data["usage_limit"] = _parse_int(value_for("usage_limit"))
        data["usage_limit_per_customer"] = _parse_int(value_for("usage_limit_per_customer"))
        data["minimum_order_amount"] = _parse_decimal(value_for("minimum_order_amount"))
        data["minimum_quantity"] = _parse_int(value_for("minimum_quantity"))
    except Exception:
        errors.append("One of the numeric limit fields is invalid.")

    data["is_active"] = _parse_bool(value_for("is_active", "true"))

    try:
        data["starts_at"] = _parse_datetime(value_for("starts_at"))
        data["ends_at"] = _parse_datetime(value_for("ends_at"))
    except Exception:
        errors.append("One of the schedule fields has an invalid datetime format.")

    partner_slug = str(value_for("partner_slug")).strip()
    data["partner_slug"] = partner_slug
    if partner_slug and not PromotionPartner.objects.filter(slug=partner_slug).exists():
        errors.append(f"Partner '{partner_slug}' does not exist.")

    if code and DiscountCode.objects.filter(code=code).exists():
        errors.append(f"Discount code '{code}' already exists.")

    return data, errors


def _preview_import_batch(batch: DiscountImportBatch) -> DiscountImportBatch:
    mapping = batch.column_mapping or {}
    defaults = batch.default_values or {}
    valid_rows = 0
    preview_codes: list[str] = []
    for row in batch.rows.all().order_by("row_number"):
        normalized_data, errors = _normalize_row(row.raw_data, mapping, defaults)
        row.normalized_data = normalized_data
        row.validation_errors = errors
        row.preview_code = normalized_data.get("code", "")
        row.is_valid = not errors
        row.save(
            update_fields=[
                "normalized_data",
                "validation_errors",
                "preview_code",
                "is_valid",
                "updated_at",
            ]
        )
        if row.is_valid:
            valid_rows += 1
            preview_codes.append(row.preview_code)

    duplicates = sorted({code for code in preview_codes if preview_codes.count(code) > 1})
    if duplicates:
        for row in batch.rows.filter(preview_code__in=duplicates):
            errors = list(row.validation_errors or [])
            errors.append("Duplicate code within this batch.")
            row.validation_errors = errors
            row.is_valid = False
            row.save(update_fields=["validation_errors", "is_valid", "updated_at"])
        valid_rows = batch.rows.filter(is_valid=True).count()

    batch.status = DiscountImportBatch.Status.PREVIEWED
    batch.valid_row_count = valid_rows
    batch.validation_summary = {
        "errors": batch.rows.filter(is_valid=False).count(),
        "duplicates": duplicates,
    }
    batch.save(update_fields=["status", "valid_row_count", "validation_summary", "updated_at"])
    return batch


def _commit_import_batch(batch: DiscountImportBatch, *, committed_by: str) -> int:
    committed = 0
    with transaction.atomic():
        for row in batch.rows.filter(is_valid=True, is_committed=False).order_by("row_number"):
            data = row.normalized_data or {}
            partner = None
            if data.get("partner_slug"):
                partner = PromotionPartner.objects.filter(slug=data["partner_slug"]).first()
            discount = DiscountCode.objects.create(
                code=data["code"],
                title=data.get("title") or data["code"],
                description=data.get("description", ""),
                value_type=data["value_type"],
                percentage_value=data.get("percentage_value"),
                fixed_amount=data.get("fixed_amount"),
                currency=data.get("currency") or "USD",
                scope=data.get("scope") or DiscountCode.DiscountScope.ORDER,
                usage_limit=data.get("usage_limit"),
                usage_limit_per_customer=data.get("usage_limit_per_customer"),
                minimum_order_amount=data.get("minimum_order_amount"),
                minimum_quantity=data.get("minimum_quantity"),
                is_active=bool(data.get("is_active", True)),
                starts_at=data.get("starts_at"),
                ends_at=data.get("ends_at"),
                attributed_partner=partner,
            )
            row.created_discount = discount
            row.is_committed = True
            row.save(update_fields=["created_discount", "is_committed", "updated_at"])
            committed += 1

        batch.status = DiscountImportBatch.Status.COMMITTED
        batch.committed_row_count = committed
        batch.committed_at = timezone.now()
        batch.committed_by = committed_by
        batch.save(
            update_fields=[
                "status",
                "committed_row_count",
                "committed_at",
                "committed_by",
                "updated_at",
            ]
        )
    return committed


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_experiment_list(request, prefix):
    refresh_experiment_snapshots()
    experiments = list(
        DiscountExperiment.objects.select_related("source_discount", "winner_variant__discount_code")
        .prefetch_related("variants")
        .order_by("-created_at")
    )
    rows = []
    for experiment in experiments:
        variants = experiment.variants.all()
        rows.append(
            {
                "detail_url": reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}),
                "cells": [
                    experiment.title,
                    experiment.get_status_display(),
                    experiment.source_discount.code,
                    str(variants.count()),
                    str(sum(variant.assignments.count() for variant in variants)),
                    experiment.winner_variant.label if experiment.winner_variant else "—",
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:discount_experiment_edit", kwargs={"prefix": prefix, "pk": experiment.pk})),
                    _post_action("Delete", reverse("dashboard:pricing:discount_experiment_delete", kwargs={"prefix": prefix, "pk": experiment.pk}), tone="danger"),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(
        request,
        "dashboard/pricing/ops/list.html",
        _ctx(
            prefix,
            "Discount Experiments",
            columns=["Experiment", "Status", "Source Code", "Variants", "Assignments", "Winner"],
            page_obj=page_obj,
            create_url=reverse("dashboard:pricing:discount_experiment_create", kwargs={"prefix": prefix}),
            create_label="Create Experiment",
            page_heading="Discount Experiments",
            page_description="Run and manage A/B tests for discount codes with winner promotion and assignment telemetry.",
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_experiment_detail(request, prefix, pk):
    refresh_experiment_snapshots()
    experiment = get_object_or_404(
        DiscountExperiment.objects.select_related("source_discount", "winner_variant__discount_code"),
        pk=pk,
    )
    variants = []
    for variant in experiment.variants.select_related("discount_code").all():
        latest_snapshot = (
            experiment.snapshots.filter(variant=variant).order_by("-created_at").first()
        )
        variants.append(
            {
                "cells": [
                    variant.label,
                    variant.discount_code.code,
                    str(variant.allocation_weight),
                    f"{getattr(latest_snapshot, 'assignments', 0)}",
                    f"{getattr(latest_snapshot, 'redemptions', 0)}",
                    f"{getattr(latest_snapshot, 'conversion_rate', Decimal('0.00')):.2%}",
                    f"{_fmt_money(getattr(latest_snapshot, 'revenue_attributed', 0))}",
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:discount_experiment_variant_edit", kwargs={"prefix": prefix, "experiment_pk": experiment.pk, "pk": variant.pk})),
                    _post_action("Promote", reverse("dashboard:pricing:discount_experiment_promote_winner", kwargs={"prefix": prefix, "experiment_pk": experiment.pk, "variant_pk": variant.pk}), tone="primary"),
                    _post_action("Delete", reverse("dashboard:pricing:discount_experiment_variant_delete", kwargs={"prefix": prefix, "experiment_pk": experiment.pk, "pk": variant.pk}), tone="danger"),
                ],
            }
        )
    latest_snapshots = DiscountExperimentSnapshot.objects.filter(experiment=experiment).order_by("-created_at")[:12]
    snapshot_rows = [
        {
            "cells": [
                snapshot.variant.label,
                str(snapshot.assignments),
                str(snapshot.redemptions),
                f"{snapshot.conversion_rate:.2%}",
                _fmt_money(snapshot.revenue_attributed),
                _fmt_money(snapshot.average_order_value),
                "Yes" if snapshot.is_winner else "—",
            ]
        }
        for snapshot in latest_snapshots
    ]
    return render(
        request,
        "dashboard/pricing/ops/detail.html",
        _ctx(
            prefix,
            f"Experiment — {experiment.title}",
            object_title=experiment.title,
            object_subtitle=experiment.description or f"Source discount: {experiment.source_discount.code}",
            back_url=reverse("dashboard:pricing:discount_experiment_list", kwargs={"prefix": prefix}),
            edit_url=reverse("dashboard:pricing:discount_experiment_edit", kwargs={"prefix": prefix, "pk": experiment.pk}),
            toolbar_actions=[
                _link_action("Add Variant", reverse("dashboard:pricing:discount_experiment_variant_create", kwargs={"prefix": prefix, "experiment_pk": experiment.pk}), tone="primary"),
                _post_action("Delete Experiment", reverse("dashboard:pricing:discount_experiment_delete", kwargs={"prefix": prefix, "pk": experiment.pk}), tone="danger"),
            ],
            summary_cards=[
                {"label": "Status", "value": experiment.get_status_display(), "helper": experiment.assignment_mode.replace("_", " ").title()},
                {"label": "Source Code", "value": experiment.source_discount.code, "helper": "Canonical control discount"},
                {"label": "Winner", "value": experiment.winner_variant.label if experiment.winner_variant else "Undecided", "helper": "Promote a winner from the variant table"},
                {"label": "Min Sample", "value": experiment.minimum_sample_size, "helper": "Assignments required before winner confidence"},
            ],
            meta_rows=[
                ("Created", _fmt_datetime(experiment.created_at)),
                ("Promoted At", _fmt_datetime(experiment.promoted_at)),
                ("Promoted By", experiment.promoted_by or "—"),
            ],
            tables=[
                {"title": "Variants", "columns": ["Label", "Discount Code", "Weight", "Assignments", "Redemptions", "Conversion", "Revenue"], "rows": variants, "empty_message": "No variants configured yet."},
                {"title": "Latest Snapshots", "columns": ["Variant", "Assignments", "Redemptions", "Conversion", "Revenue", "AOV", "Winner"], "rows": snapshot_rows, "empty_message": "No experiment snapshots captured yet."},
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_experiment_create(request, prefix):
    form = DiscountExperimentForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            experiment = form.save()
            messages.success(request, "Discount experiment created.")
            return redirect(reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}))
        messages.error(request, "Please correct the experiment form errors below.")
    return render(
        request,
        "dashboard/pricing/ops/form.html",
        _ctx(
            prefix,
            "Create Discount Experiment",
            form=form,
            form_title="Create Discount Experiment",
            form_description="Create a code experiment, then attach variants and begin assignment tracking.",
            submit_label="Create Experiment",
            cancel_url=reverse("dashboard:pricing:discount_experiment_list", kwargs={"prefix": prefix}),
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_experiment_edit(request, prefix, pk):
    experiment = get_object_or_404(DiscountExperiment, pk=pk)
    form = DiscountExperimentForm(request.POST or None, instance=experiment)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Experiment updated.")
            return redirect(reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}))
        messages.error(request, "Please correct the experiment form errors below.")
    return render(
        request,
        "dashboard/pricing/ops/form.html",
        _ctx(
            prefix,
            f"Edit Experiment — {experiment.title}",
            form=form,
            form_title=f"Edit Experiment — {experiment.title}",
            submit_label="Save Experiment",
            cancel_url=reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}),
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_experiment_variant_create(request, prefix, experiment_pk):
    experiment = get_object_or_404(DiscountExperiment, pk=experiment_pk)
    form = DiscountExperimentVariantForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            variant = form.save(commit=False)
            variant.experiment = experiment
            variant.save()
            messages.success(request, "Experiment variant added.")
            return redirect(reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}))
        messages.error(request, "Please correct the variant form errors below.")
    return render(
        request,
        "dashboard/pricing/ops/form.html",
        _ctx(
            prefix,
            f"Add Variant — {experiment.title}",
            form=form,
            form_title=f"Add Variant — {experiment.title}",
            submit_label="Save Variant",
            cancel_url=reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}),
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_experiment_variant_edit(request, prefix, experiment_pk, pk):
    experiment = get_object_or_404(DiscountExperiment, pk=experiment_pk)
    variant = get_object_or_404(DiscountExperimentVariant, pk=pk, experiment=experiment)
    form = DiscountExperimentVariantForm(request.POST or None, instance=variant)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Experiment variant updated.")
            return redirect(reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}))
        messages.error(request, "Please correct the variant form errors below.")
    return render(
        request,
        "dashboard/pricing/ops/form.html",
        _ctx(
            prefix,
            f"Edit Variant — {variant.label}",
            form=form,
            form_title=f"Edit Variant — {variant.label}",
            submit_label="Save Variant",
            cancel_url=reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}),
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def discount_experiment_promote_winner(request, prefix, experiment_pk, variant_pk):
    experiment = get_object_or_404(DiscountExperiment, pk=experiment_pk)
    winner = get_object_or_404(DiscountExperimentVariant, pk=variant_pk, experiment=experiment)
    with transaction.atomic():
        source = experiment.source_discount
        variant_discount = winner.discount_code
        source.value_type = variant_discount.value_type
        source.percentage_value = variant_discount.percentage_value
        source.fixed_amount = variant_discount.fixed_amount
        source.currency = variant_discount.currency
        source.free_item_variant = variant_discount.free_item_variant
        source.buy_x_get_y_promotion = variant_discount.buy_x_get_y_promotion
        source.scope = variant_discount.scope
        source.allocation_method = variant_discount.allocation_method
        source.usage_limit = variant_discount.usage_limit
        source.usage_limit_per_customer = variant_discount.usage_limit_per_customer
        source.minimum_order_amount = variant_discount.minimum_order_amount
        source.minimum_quantity = variant_discount.minimum_quantity
        source.requires_first_order = variant_discount.requires_first_order
        source.customer_eligibility = variant_discount.customer_eligibility
        source.max_discount_amount = variant_discount.max_discount_amount
        source.total_stack_cap_amount = variant_discount.total_stack_cap_amount
        source.eligible_countries = variant_discount.eligible_countries
        source.eligible_states = variant_discount.eligible_states
        source.eligible_cities = variant_discount.eligible_cities
        source.save()

        experiment.winner_variant = winner
        experiment.status = DiscountExperiment.Status.COMPLETED
        experiment.promoted_at = timezone.now()
        experiment.promoted_by = getattr(request.user, "email", "") or getattr(request.user, "username", "")
        experiment.save(update_fields=["winner_variant", "status", "promoted_at", "promoted_by", "updated_at"])

        experiment.variants.exclude(pk=winner.pk).update(is_active=False)
    messages.success(request, f"{winner.label} has been promoted as the winning discount variant.")
    return redirect(reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_compatibility_rule_list(request, prefix):
    rules = list(
        PromotionCompatibilityRule.objects.select_related(
            "left_discount_code",
            "left_automatic_discount",
            "right_discount_code",
            "right_automatic_discount",
        ).order_by("-created_at")
    )
    rows = []
    for rule in rules:
        left_label = getattr(rule.left_object, "code", None) or getattr(rule.left_object, "title", "—")
        right_label = getattr(rule.right_object, "code", None) or getattr(rule.right_object, "title", "—")
        rows.append(
            {
                "cells": [
                    left_label,
                    right_label,
                    rule.get_resolution_display(),
                    _fmt_money(rule.max_combined_discount_amount) if rule.max_combined_discount_amount else "—",
                    "Active" if rule.is_active else "Inactive",
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:promotion_compatibility_rule_edit", kwargs={"prefix": prefix, "pk": rule.pk})),
                    _post_action("Delete", reverse("dashboard:pricing:promotion_compatibility_rule_delete", kwargs={"prefix": prefix, "pk": rule.pk}), tone="danger"),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(
        request,
        "dashboard/pricing/ops/list.html",
        _ctx(
            prefix,
            "Promotion Compatibility Rules",
            columns=["Left Promotion", "Right Promotion", "Resolution", "Stack Cap", "Status"],
            page_obj=page_obj,
            create_url=reverse("dashboard:pricing:promotion_compatibility_rule_create", kwargs={"prefix": prefix}),
            create_label="Add Rule",
            page_heading="Promotion Compatibility Rules",
            page_description="Define explicit stacking, denial, and preference rules between codes and automatic discounts.",
            toolbar_actions=[
                _link_action("View Conflicts", reverse("dashboard:pricing:promotion_conflict_list", kwargs={"prefix": prefix}), tone="primary"),
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_compatibility_rule_create(request, prefix):
    form = PromotionCompatibilityRuleForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Compatibility rule saved.")
            return redirect(reverse("dashboard:pricing:promotion_compatibility_rule_list", kwargs={"prefix": prefix}))
        messages.error(request, "Please correct the compatibility rule errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Add Compatibility Rule", form=form, form_title="Add Compatibility Rule", submit_label="Save Rule", cancel_url=reverse("dashboard:pricing:promotion_compatibility_rule_list", kwargs={"prefix": prefix})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_compatibility_rule_edit(request, prefix, pk):
    rule = get_object_or_404(PromotionCompatibilityRule, pk=pk)
    form = PromotionCompatibilityRuleForm(request.POST or None, instance=rule)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Compatibility rule updated.")
            return redirect(reverse("dashboard:pricing:promotion_compatibility_rule_list", kwargs={"prefix": prefix}))
        messages.error(request, "Please correct the compatibility rule errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Edit Compatibility Rule", form=form, form_title="Edit Compatibility Rule", submit_label="Save Rule", cancel_url=reverse("dashboard:pricing:promotion_compatibility_rule_list", kwargs={"prefix": prefix})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def promotion_compatibility_rule_delete(request, prefix, pk):
    rule = get_object_or_404(PromotionCompatibilityRule, pk=pk)
    rule.delete()
    messages.success(request, "Compatibility rule deleted.")
    return redirect(reverse("dashboard:pricing:promotion_compatibility_rule_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_conflict_list(request, prefix):
    conflicts = list(
        PromotionConflictRecord.objects.select_related(
            "left_discount_code",
            "left_automatic_discount",
            "right_discount_code",
            "right_automatic_discount",
        ).order_by("-created_at")
    )
    rows = []
    for conflict in conflicts:
        left_label = getattr(conflict.left_discount_code, "code", None) or getattr(conflict.left_automatic_discount, "title", "—")
        right_label = getattr(conflict.right_discount_code, "code", None) or getattr(conflict.right_automatic_discount, "title", "—")
        rows.append(
            {
                "cells": [
                    conflict.summary,
                    f"{left_label} ↔ {right_label}",
                    conflict.get_severity_display(),
                    conflict.get_status_display(),
                    _fmt_datetime(conflict.created_at),
                ],
                "actions": [
                    _post_action("Acknowledge", reverse("dashboard:pricing:promotion_conflict_acknowledge", kwargs={"prefix": prefix, "pk": conflict.pk})),
                    _post_action("Resolve", reverse("dashboard:pricing:promotion_conflict_resolve", kwargs={"prefix": prefix, "pk": conflict.pk}), tone="primary"),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(
        request,
        "dashboard/pricing/ops/list.html",
        _ctx(
            prefix,
            "Promotion Conflicts",
            columns=["Summary", "Promotions", "Severity", "Status", "Detected"],
            page_obj=page_obj,
            page_heading="Promotion Conflicts",
            page_description="Review overlapping promotions that may produce contradictory stack behavior or merchant confusion.",
            toolbar_actions=[
                _post_action("Refresh Conflicts", reverse("dashboard:pricing:promotion_conflict_refresh", kwargs={"prefix": prefix}), tone="primary"),
                _link_action("Compatibility Rules", reverse("dashboard:pricing:promotion_compatibility_rule_list", kwargs={"prefix": prefix})),
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def promotion_conflict_refresh(request, prefix):
    created = refresh_promotion_conflicts()
    messages.success(request, f"Conflict scan complete. {created} open conflicts recorded.")
    return redirect(reverse("dashboard:pricing:promotion_conflict_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def promotion_conflict_acknowledge(request, prefix, pk):
    conflict = get_object_or_404(PromotionConflictRecord, pk=pk)
    conflict.status = PromotionConflictRecord.Status.ACKNOWLEDGED
    conflict.acknowledged_at = timezone.now()
    conflict.acknowledged_by = getattr(request.user, "email", "") or getattr(request.user, "username", "")
    conflict.save(update_fields=["status", "acknowledged_at", "acknowledged_by", "updated_at"])
    messages.success(request, "Conflict acknowledged.")
    return redirect(reverse("dashboard:pricing:promotion_conflict_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def promotion_conflict_resolve(request, prefix, pk):
    conflict = get_object_or_404(PromotionConflictRecord, pk=pk)
    conflict.status = PromotionConflictRecord.Status.RESOLVED
    conflict.resolved_at = timezone.now()
    conflict.save(update_fields=["status", "resolved_at", "updated_at"])
    messages.success(request, "Conflict resolved.")
    return redirect(reverse("dashboard:pricing:promotion_conflict_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_import_batch_list(request, prefix):
    batches = list(DiscountImportBatch.objects.order_by("-created_at"))
    rows = []
    for batch in batches:
        rows.append(
            {
                "detail_url": reverse("dashboard:pricing:discount_import_batch_detail", kwargs={"prefix": prefix, "pk": batch.pk}),
                "cells": [
                    batch.title,
                    batch.get_status_display(),
                    str(batch.row_count),
                    str(batch.valid_row_count),
                    str(batch.committed_row_count),
                    _fmt_datetime(batch.created_at),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(
        request,
        "dashboard/pricing/ops/list.html",
        _ctx(
            prefix,
            "Discount Imports",
            columns=["Batch", "Status", "Rows", "Valid", "Committed", "Created"],
            page_obj=page_obj,
            create_url=reverse("dashboard:pricing:discount_import_batch_create", kwargs={"prefix": prefix}),
            create_label="Upload CSV",
            page_heading="Discount Import Batches",
            page_description="Stage, preview, validate, and commit discount code imports safely before they affect the live catalog.",
            toolbar_actions=[
                _link_action("Export All Codes", reverse("dashboard:pricing:discount_code_export_all_csv", kwargs={"prefix": prefix}), tone="primary"),
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_import_batch_create(request, prefix):
    form = DiscountImportUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            csv_file = form.cleaned_data["csv_file"]
            decoded = csv_file.read().decode("utf-8-sig")
            reader = csv.DictReader(StringIO(decoded))
            headers = list(reader.fieldnames or [])
            if not headers:
                messages.error(request, "The uploaded CSV file does not contain any headers.")
            else:
                batch = DiscountImportBatch.objects.create(
                    title=form.cleaned_data["title"],
                    source_filename=getattr(csv_file, "name", ""),
                    column_mapping=_guess_mapping(headers),
                    default_values={
                        "value_type": form.cleaned_data.get("default_value_type") or "",
                        "scope": form.cleaned_data.get("default_scope") or "",
                        "currency": (form.cleaned_data.get("default_currency") or "").upper(),
                    },
                )
                row_count = 0
                for row_number, row in enumerate(reader, start=2):
                    DiscountImportRow.objects.create(
                        batch=batch,
                        row_number=row_number,
                        raw_data=row,
                    )
                    row_count += 1
                batch.row_count = row_count
                batch.save(update_fields=["row_count", "updated_at"])
                _preview_import_batch(batch)
                messages.success(request, "Import batch uploaded and previewed.")
                return redirect(reverse("dashboard:pricing:discount_import_batch_detail", kwargs={"prefix": prefix, "pk": batch.pk}))
        else:
            messages.error(request, "Please correct the upload form errors below.")
    return render(
        request,
        "dashboard/pricing/ops/form.html",
        _ctx(
            prefix,
            "Upload Discount CSV",
            form=form,
            form_title="Upload Discount CSV",
            form_description="Upload a code-centric CSV, then preview mapping and validation results before committing any live discounts.",
            submit_label="Upload & Preview",
            cancel_url=reverse("dashboard:pricing:discount_import_batch_list", kwargs={"prefix": prefix}),
            form_enctype="multipart/form-data",
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_import_batch_detail(request, prefix, pk):
    batch = get_object_or_404(DiscountImportBatch, pk=pk)
    first_row = batch.rows.order_by("row_number").first()
    headers = list((first_row.raw_data or {}).keys()) if first_row else []

    if request.method == "POST" and request.POST.get("action") == "update_mapping":
        mapping_form = DiscountImportMappingForm(request.POST, headers=headers)
        if mapping_form.is_valid():
            batch.column_mapping = {key: value for key, value in mapping_form.cleaned_data.items() if value}
            batch.save(update_fields=["column_mapping", "updated_at"])
            _preview_import_batch(batch)
            messages.success(request, "Import mapping updated and preview regenerated.")
            return redirect(reverse("dashboard:pricing:discount_import_batch_detail", kwargs={"prefix": prefix, "pk": batch.pk}))
    else:
        mapping_form = DiscountImportMappingForm(headers=headers, initial=batch.column_mapping)

    preview_rows = list(batch.rows.order_by("row_number")[:50])
    return render(
        request,
        "dashboard/pricing/ops/import_batch_detail.html",
        _ctx(
            prefix,
            f"Import Batch — {batch.title}",
            batch=batch,
            mapping_form=mapping_form,
            preview_rows=preview_rows,
            back_url=reverse("dashboard:pricing:discount_import_batch_list", kwargs={"prefix": prefix}),
            commit_url=reverse("dashboard:pricing:discount_import_batch_commit", kwargs={"prefix": prefix, "pk": batch.pk}),
            error_report_url=reverse("dashboard:pricing:discount_import_batch_error_report", kwargs={"prefix": prefix, "pk": batch.pk}),
            rows_export_url=reverse("dashboard:pricing:discount_import_batch_rows_export", kwargs={"prefix": prefix, "pk": batch.pk}),
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def discount_import_batch_commit(request, prefix, pk):
    batch = get_object_or_404(DiscountImportBatch, pk=pk)
    if batch.status == DiscountImportBatch.Status.COMMITTED:
        messages.info(request, "This import batch has already been committed.")
    else:
        committed = _commit_import_batch(
            batch,
            committed_by=getattr(request.user, "email", "") or getattr(request.user, "username", ""),
        )
        messages.success(request, f"Committed {committed} discount codes from the import batch.")
    return redirect(reverse("dashboard:pricing:discount_import_batch_detail", kwargs={"prefix": prefix, "pk": batch.pk}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_code_export_all_csv(request, prefix):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="discount-codes-export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "code",
            "title",
            "value_type",
            "percentage_value",
            "fixed_amount",
            "currency",
            "scope",
            "usage_limit",
            "usage_count",
            "per_customer_limit",
            "is_active",
            "partner",
            "experiments",
            "starts_at",
            "ends_at",
        ]
    )
    for code in DiscountCode.objects.select_related("attributed_partner").prefetch_related("experiments").order_by("code"):
        writer.writerow(
            [
                code.code,
                code.title,
                code.value_type,
                code.percentage_value or "",
                code.fixed_amount or "",
                code.currency,
                code.scope,
                code.usage_limit or "",
                code.usage_count,
                code.usage_limit_per_customer or "",
                "true" if code.is_active else "false",
                code.attributed_partner.slug if code.attributed_partner else "",
                ", ".join(code.experiments.values_list("title", flat=True)),
                code.starts_at.isoformat() if code.starts_at else "",
                code.ends_at.isoformat() if code.ends_at else "",
            ]
        )
    return response


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def pricing_automation_rule_list(request, prefix):
    rules = list(PricingAutomationRule.objects.select_related("source_discount", "target_group").order_by("name"))
    rows = []
    for rule in rules:
        rows.append(
            {
                "detail_url": reverse("dashboard:pricing:pricing_automation_rule_detail", kwargs={"prefix": prefix, "pk": rule.pk}),
                "cells": [
                    rule.name,
                    rule.get_trigger_type_display(),
                    rule.source_discount.code,
                    rule.get_delivery_mode_display(),
                    str(rule.issued_count),
                    _fmt_datetime(rule.last_run_at),
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:pricing_automation_rule_edit", kwargs={"prefix": prefix, "pk": rule.pk})),
                    _post_action("Delete", reverse("dashboard:pricing:pricing_automation_rule_delete", kwargs={"prefix": prefix, "pk": rule.pk}), tone="danger"),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(
        request,
        "dashboard/pricing/ops/list.html",
        _ctx(
            prefix,
            "Pricing Automation",
            columns=["Rule", "Trigger", "Source Discount", "Delivery", "Issued", "Last Run"],
            page_obj=page_obj,
            create_url=reverse("dashboard:pricing:pricing_automation_rule_create", kwargs={"prefix": prefix}),
            create_label="Add Automation Rule",
            page_heading="Pricing Automation",
            page_description="Run trigger-based discount delivery using cron-safe rules, issued-code ledgers, and queued notification jobs.",
            toolbar_actions=[
                _post_action("Run Automation", reverse("dashboard:pricing:pricing_automation_run_now", kwargs={"prefix": prefix}), tone="primary"),
                _post_action("Process Jobs", reverse("dashboard:pricing:pricing_notification_jobs_run_now", kwargs={"prefix": prefix})),
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def pricing_automation_rule_detail(request, prefix, pk):
    rule = get_object_or_404(PricingAutomationRule.objects.select_related("source_discount", "target_group"), pk=pk)
    issued_rows = []
    for issued in rule.issued_codes.select_related("customer", "discount_code").order_by("-created_at")[:25]:
        issued_rows.append(
            {
                "cells": [
                    issued.discount_code.code,
                    getattr(getattr(issued.customer, "user", None), "email", "") or "Guest / unknown",
                    issued.get_status_display(),
                    _fmt_datetime(issued.delivered_at),
                    _fmt_datetime(issued.redeemed_at),
                ]
            }
        )
    log_rows = []
    for log in rule.delivery_logs.select_related("customer").order_by("-created_at")[:25]:
        log_rows.append(
            {
                "cells": [
                    getattr(getattr(log.customer, "user", None), "email", "") or "Guest / unknown",
                    log.channel or "—",
                    log.result,
                    log.order_number or "—",
                    _fmt_datetime(log.created_at),
                ]
            }
        )
    return render(
        request,
        "dashboard/pricing/ops/detail.html",
        _ctx(
            prefix,
            f"Automation Rule — {rule.name}",
            object_title=rule.name,
            object_subtitle=rule.source_discount.code,
            back_url=reverse("dashboard:pricing:pricing_automation_rule_list", kwargs={"prefix": prefix}),
            edit_url=reverse("dashboard:pricing:pricing_automation_rule_edit", kwargs={"prefix": prefix, "pk": rule.pk}),
            toolbar_actions=[
                _post_action("Run Rule Engine", reverse("dashboard:pricing:pricing_automation_run_now", kwargs={"prefix": prefix}), tone="primary"),
                _post_action("Delete Rule", reverse("dashboard:pricing:pricing_automation_rule_delete", kwargs={"prefix": prefix, "pk": rule.pk}), tone="danger"),
            ],
            summary_cards=[
                {"label": "Trigger", "value": rule.get_trigger_type_display(), "helper": rule.get_delivery_mode_display()},
                {"label": "Issued", "value": rule.issued_count, "helper": "Codes issued by this rule"},
                {"label": "Runs", "value": rule.run_count, "helper": f"Last run: {_fmt_datetime(rule.last_run_at)}"},
                {"label": "Target Group", "value": rule.target_group.name if rule.target_group else "All customers", "helper": "Optional segment filter"},
            ],
            meta_rows=[
                ("Delay (minutes)", rule.delay_minutes),
                ("Evaluation Window (days)", rule.evaluation_window_days),
                ("Issue Prefix", rule.issue_prefix or "—"),
                ("Requires Verified Customer", "Yes" if rule.requires_verified_customer else "No"),
                ("Config", json.dumps(rule.config, indent=2) if rule.config else "—"),
            ],
            tables=[
                {"title": "Issued Codes", "columns": ["Discount Code", "Customer", "Status", "Delivered", "Redeemed"], "rows": issued_rows, "empty_message": "No issued codes recorded yet."},
                {"title": "Delivery Logs", "columns": ["Customer", "Channel", "Result", "Order", "Created"], "rows": log_rows, "empty_message": "No delivery logs recorded yet."},
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def pricing_automation_rule_create(request, prefix):
    form = PricingAutomationRuleForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            rule = form.save()
            messages.success(request, "Automation rule created.")
            return redirect(reverse("dashboard:pricing:pricing_automation_rule_detail", kwargs={"prefix": prefix, "pk": rule.pk}))
        messages.error(request, "Please correct the automation rule errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Create Automation Rule", form=form, form_title="Create Automation Rule", submit_label="Save Rule", cancel_url=reverse("dashboard:pricing:pricing_automation_rule_list", kwargs={"prefix": prefix})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def pricing_automation_rule_edit(request, prefix, pk):
    rule = get_object_or_404(PricingAutomationRule, pk=pk)
    form = PricingAutomationRuleForm(request.POST or None, instance=rule)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Automation rule updated.")
            return redirect(reverse("dashboard:pricing:pricing_automation_rule_detail", kwargs={"prefix": prefix, "pk": rule.pk}))
        messages.error(request, "Please correct the automation rule errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Edit Automation Rule", form=form, form_title="Edit Automation Rule", submit_label="Save Rule", cancel_url=reverse("dashboard:pricing:pricing_automation_rule_detail", kwargs={"prefix": prefix, "pk": rule.pk})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def pricing_automation_run_now(request, prefix):
    summary = run_pricing_automation()
    messages.success(request, f"Automation run complete. {summary.rules_run} rules evaluated, {summary.deliveries_created} deliveries queued.")
    return redirect(reverse("dashboard:pricing:pricing_automation_rule_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def pricing_notification_jobs_run_now(request, prefix):
    result = process_due_notification_jobs(limit=250)
    messages.success(request, f"Processed queued notification jobs. Sent: {result.get('sent', 0)}, failed: {result.get('failed', 0)}.")
    return redirect(reverse("dashboard:pricing:pricing_automation_rule_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_partner_list(request, prefix):
    partners = list(
        PromotionPartner.objects.annotate(
            code_count=Count("discount_codes", distinct=True),
            commission_total=Sum("commission_entries__commission_amount"),
            revenue_total=Sum("commission_entries__revenue_attributed"),
        ).order_by("name")
    )
    rows = []
    for partner in partners:
        rows.append(
            {
                "detail_url": reverse("dashboard:pricing:promotion_partner_detail", kwargs={"prefix": prefix, "pk": partner.pk}),
                "cells": [
                    partner.name,
                    partner.get_partner_type_display(),
                    str(partner.code_count or 0),
                    _fmt_money(partner.revenue_total or 0),
                    _fmt_money(partner.commission_total or 0),
                    "Active" if partner.is_active else "Inactive",
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:promotion_partner_edit", kwargs={"prefix": prefix, "pk": partner.pk})),
                    _link_action("Links", reverse("dashboard:pricing:promotion_link_list", kwargs={"prefix": prefix}) + f"?partner={partner.pk}"),
                    _post_action("Delete", reverse("dashboard:pricing:promotion_partner_delete", kwargs={"prefix": prefix, "pk": partner.pk}), tone="danger"),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(request, "dashboard/pricing/ops/list.html", _ctx(prefix, "Promotion Partners", columns=["Partner", "Type", "Codes", "Revenue", "Commission", "Status"], page_obj=page_obj, create_url=reverse("dashboard:pricing:promotion_partner_create", kwargs={"prefix": prefix}), create_label="Add Partner", page_heading="Promotion Partners", page_description="Manage influencer, referral, campaign, and affiliate attribution sources with commission tracking and share links."))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_partner_detail(request, prefix, pk):
    partner = get_object_or_404(PromotionPartner, pk=pk)
    share_link = build_promotion_link(partner=partner, landing_path="/promotions/referrals/join/")
    codes = partner.discount_codes.order_by("code")
    code_rows = []
    for code in codes:
        link = build_promotion_link(discount_code=code, partner=partner)
        code_rows.append(
            {
                "cells": [
                    code.code,
                    code.title,
                    code.value_type,
                    str(code.usage_count),
                    link.slug,
                ],
                "actions": [
                    _link_action("Share Link", reverse("dashboard:pricing:promotion_link_detail", kwargs={"prefix": prefix, "pk": link.pk})),
                ],
            }
        )
    commission_rows = [
        {
            "cells": [
                entry.order_number,
                entry.discount_code.code if entry.discount_code else "—",
                _fmt_money(entry.revenue_attributed),
                _fmt_money(entry.commission_amount),
                entry.get_status_display(),
            ]
        }
        for entry in partner.commission_entries.select_related("discount_code").order_by("-created_at")[:25]
    ]
    generation_form = PartnerDiscountGenerationForm()
    return render(
        request,
        "dashboard/pricing/ops/detail.html",
        _ctx(
            prefix,
            f"Partner — {partner.name}",
            object_title=partner.name,
            object_subtitle=f"{partner.get_partner_type_display()} · {partner.email or 'No email set'}",
            back_url=reverse("dashboard:pricing:promotion_partner_list", kwargs={"prefix": prefix}),
            edit_url=reverse("dashboard:pricing:promotion_partner_edit", kwargs={"prefix": prefix, "pk": partner.pk}),
            toolbar_actions=[
                _link_action("Generate Code", reverse("dashboard:pricing:promotion_partner_generate_code", kwargs={"prefix": prefix, "pk": partner.pk}), tone="primary"),
                _link_action("Manage Share Links", reverse("dashboard:pricing:promotion_link_list", kwargs={"prefix": prefix}) + f"?partner={partner.pk}"),
                _post_action("Delete Partner", reverse("dashboard:pricing:promotion_partner_delete", kwargs={"prefix": prefix, "pk": partner.pk}), tone="danger"),
            ],
            summary_cards=[
                {"label": "Primary Share Link", "value": share_link.slug, "helper": share_link.landing_path},
                {"label": "Code Prefix", "value": partner.code_prefix or "—", "helper": partner.referral_slug},
                {"label": "Revenue", "value": _fmt_money(partner.commission_entries.filter(status=PromotionCommissionLedger.LedgerStatus.EARNED).aggregate(total=Sum("revenue_attributed"))["total"] or 0), "helper": "Attributed order revenue"},
                {"label": "Commission", "value": _fmt_money(partner.commission_entries.filter(status=PromotionCommissionLedger.LedgerStatus.EARNED).aggregate(total=Sum("commission_amount"))["total"] or 0), "helper": f"Rate {partner.commission_rate_percentage}%"},
            ],
            meta_rows=[
                ("Referral Slug", partner.referral_slug or "—"),
                ("Default UTM Source", partner.default_utm_source or "—"),
                ("Default UTM Medium", partner.default_utm_medium or "—"),
                ("Default UTM Campaign", partner.default_utm_campaign or "—"),
                ("QR Payload", strip_tags(share_link.qr_svg)[:120] + "…" if share_link.qr_svg else "—"),
            ],
            tables=[
                {"title": "Attributed Discount Codes", "columns": ["Code", "Title", "Type", "Uses", "Share Slug"], "rows": code_rows, "empty_message": "No attributed discount codes yet."},
                {"title": "Commission Ledger", "columns": ["Order", "Discount Code", "Revenue", "Commission", "Status"], "rows": commission_rows, "empty_message": "No commission entries recorded yet."},
            ],
            inline_form=generation_form,
            inline_form_action=reverse("dashboard:pricing:promotion_partner_generate_code", kwargs={"prefix": prefix, "pk": partner.pk}),
            inline_form_title="Generate Attributed Code",
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_partner_create(request, prefix):
    form = PromotionPartnerForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            partner = form.save()
            messages.success(request, "Promotion partner created.")
            return redirect(reverse("dashboard:pricing:promotion_partner_detail", kwargs={"prefix": prefix, "pk": partner.pk}))
        messages.error(request, "Please correct the partner form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Create Promotion Partner", form=form, form_title="Create Promotion Partner", submit_label="Save Partner", cancel_url=reverse("dashboard:pricing:promotion_partner_list", kwargs={"prefix": prefix})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_partner_edit(request, prefix, pk):
    partner = get_object_or_404(PromotionPartner, pk=pk)
    form = PromotionPartnerForm(request.POST or None, instance=partner)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Promotion partner updated.")
            return redirect(reverse("dashboard:pricing:promotion_partner_detail", kwargs={"prefix": prefix, "pk": partner.pk}))
        messages.error(request, "Please correct the partner form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Edit Promotion Partner", form=form, form_title="Edit Promotion Partner", submit_label="Save Partner", cancel_url=reverse("dashboard:pricing:promotion_partner_detail", kwargs={"prefix": prefix, "pk": partner.pk})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["GET", "POST"])
def promotion_partner_generate_code(request, prefix, pk):
    partner = get_object_or_404(PromotionPartner, pk=pk)
    form = PartnerDiscountGenerationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    source_discount = form.cleaned_data["source_discount"]
                    title = form.cleaned_data["title"] or f"{partner.name} — {source_discount.title}"
                    cloned_discount = _clone_discount_code(
                        source_discount,
                        code=form.cleaned_data["code"],
                        title=title,
                        partner=partner,
                    )
                    build_promotion_link(
                        discount_code=cloned_discount,
                        partner=partner,
                        landing_path=form.cleaned_data.get("share_path") or "/promotions/coupons/",
                    )
                messages.success(request, f"Generated attributed code {cloned_discount.code} for {partner.name}.")
                return redirect(reverse("dashboard:pricing:promotion_partner_detail", kwargs={"prefix": prefix, "pk": partner.pk}))
            except Exception as exc:
                messages.error(request, f"Unable to generate partner code: {exc}")
        else:
            messages.error(request, "Please correct the code generation form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Generate Partner Discount Code", form=form, form_title=f"Generate Code — {partner.name}", submit_label="Generate Code", cancel_url=reverse("dashboard:pricing:promotion_partner_detail", kwargs={"prefix": prefix, "pk": partner.pk})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def bundle_offer_list(request, prefix):
    bundles = list(
        BundleOffer.objects.annotate(
            item_count=Count("items", distinct=True),
            attributed_orders=Count("order_ledgers", distinct=True),
            revenue_total=Sum("order_ledgers__revenue_attributed"),
        ).order_by("-created_at")
    )
    rows = []
    for bundle in bundles:
        rows.append(
            {
                "detail_url": reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk}),
                "cells": [
                    bundle.name,
                    bundle.get_offer_type_display(),
                    str(bundle.item_count or 0),
                    str(bundle.attributed_orders or 0),
                    _fmt_money(bundle.revenue_total or 0),
                    "Public" if bundle.is_public else "Private",
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:bundle_offer_edit", kwargs={"prefix": prefix, "pk": bundle.pk})),
                    _link_action("Links", reverse("dashboard:pricing:promotion_link_list", kwargs={"prefix": prefix}) + f"?bundle={bundle.pk}"),
                    _post_action("Delete", reverse("dashboard:pricing:bundle_offer_delete", kwargs={"prefix": prefix, "pk": bundle.pk}), tone="danger"),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(request, "dashboard/pricing/ops/list.html", _ctx(prefix, "Bundle Offers", columns=["Bundle", "Type", "Items", "Orders", "Revenue", "Visibility"], page_obj=page_obj, create_url=reverse("dashboard:pricing:bundle_offer_create", kwargs={"prefix": prefix}), create_label="Create Bundle", page_heading="Bundle Offers", page_description="Manage fixed, mix-and-match, and upsell bundles with shared storefront landing pages and order attribution."))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def bundle_offer_detail(request, prefix, pk):
    bundle = get_object_or_404(BundleOffer, pk=pk)
    share_link = build_promotion_link(bundle=bundle)
    item_rows = []
    for item in bundle.items.select_related("product", "variant__product", "category").order_by("sort_order", "created_at"):
        target = item.variant or item.product or item.category
        target_label = getattr(target, "name", None) or getattr(target, "variant_name", None) or str(target)
        discount_label = item.discount_percentage if item.discount_percentage is not None else item.discounted_unit_price or "—"
        item_rows.append(
            {
                "cells": [
                    item.get_role_display(),
                    target_label,
                    str(item.quantity),
                    str(discount_label),
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:bundle_offer_item_edit", kwargs={"prefix": prefix, "bundle_pk": bundle.pk, "pk": item.pk})),
                    _post_action("Delete", reverse("dashboard:pricing:bundle_offer_item_delete", kwargs={"prefix": prefix, "bundle_pk": bundle.pk, "pk": item.pk}), tone="danger"),
                ],
            }
        )
    ledger_rows = [
        {
            "cells": [
                ledger.order_number,
                str(ledger.quantity),
                _fmt_money(ledger.bundle_discount_amount),
                _fmt_money(ledger.revenue_attributed),
                _fmt_datetime(ledger.created_at),
            ]
        }
        for ledger in bundle.order_ledgers.order_by("-created_at")[:25]
    ]
    return render(
        request,
        "dashboard/pricing/ops/detail.html",
        _ctx(
            prefix,
            f"Bundle — {bundle.name}",
            object_title=bundle.name,
            object_subtitle=bundle.public_title or bundle.description,
            back_url=reverse("dashboard:pricing:bundle_offer_list", kwargs={"prefix": prefix}),
            edit_url=reverse("dashboard:pricing:bundle_offer_edit", kwargs={"prefix": prefix, "pk": bundle.pk}),
            toolbar_actions=[
                _link_action("Add Bundle Item", reverse("dashboard:pricing:bundle_offer_item_create", kwargs={"prefix": prefix, "bundle_pk": bundle.pk}), tone="primary"),
                _link_action("Public Page", reverse("product:bundle_detail", kwargs={"bundle_slug": bundle.slug})),
                _link_action("Manage Share Link", reverse("dashboard:pricing:promotion_link_list", kwargs={"prefix": prefix}) + f"?bundle={bundle.pk}"),
                _post_action("Delete Bundle", reverse("dashboard:pricing:bundle_offer_delete", kwargs={"prefix": prefix, "pk": bundle.pk}), tone="danger"),
            ],
            summary_cards=[
                {"label": "Bundle Type", "value": bundle.get_offer_type_display(), "helper": share_link.slug},
                {"label": "Bundle Price", "value": f"{bundle.currency} {_fmt_money(bundle.bundle_price or 0)}", "helper": "Shared landing price"},
                {"label": "Required Qty", "value": bundle.required_quantity, "helper": f"Selections {bundle.min_selection}–{bundle.max_selection or '∞'}"},
                {"label": "Orders", "value": bundle.order_ledgers.count(), "helper": "Orders attributed to bundle pricing"},
            ],
            meta_rows=[
                ("Badge", bundle.badge_label or "—"),
                ("Share Copy", bundle.share_copy or "—"),
                ("Visibility", "Public" if bundle.is_public else "Private"),
                ("Share Slug", share_link.slug),
            ],
            tables=[
                {"title": "Bundle Items", "columns": ["Role", "Target", "Qty", "Discount"], "rows": item_rows, "empty_message": "No bundle items configured yet."},
                {"title": "Bundle Order Ledger", "columns": ["Order", "Qty", "Discount", "Revenue", "Created"], "rows": ledger_rows, "empty_message": "No bundle orders recorded yet."},
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def bundle_offer_create(request, prefix):
    form = BundleOfferForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            bundle = form.save()
            messages.success(request, "Bundle offer created.")
            return redirect(reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk}))
        messages.error(request, "Please correct the bundle form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Create Bundle Offer", form=form, form_title="Create Bundle Offer", submit_label="Save Bundle", cancel_url=reverse("dashboard:pricing:bundle_offer_list", kwargs={"prefix": prefix})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def bundle_offer_edit(request, prefix, pk):
    bundle = get_object_or_404(BundleOffer, pk=pk)
    form = BundleOfferForm(request.POST or None, instance=bundle)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Bundle offer updated.")
            return redirect(reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk}))
        messages.error(request, "Please correct the bundle form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Edit Bundle Offer", form=form, form_title="Edit Bundle Offer", submit_label="Save Bundle", cancel_url=reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def bundle_offer_item_create(request, prefix, bundle_pk):
    bundle = get_object_or_404(BundleOffer, pk=bundle_pk)
    form = BundleOfferItemForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            item = form.save(commit=False)
            item.bundle = bundle
            item.save()
            messages.success(request, "Bundle item saved.")
            return redirect(reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk}))
        messages.error(request, "Please correct the bundle item form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Add Bundle Item", form=form, form_title=f"Add Bundle Item — {bundle.name}", submit_label="Save Item", cancel_url=reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def bundle_offer_item_edit(request, prefix, bundle_pk, pk):
    bundle = get_object_or_404(BundleOffer, pk=bundle_pk)
    item = get_object_or_404(BundleOfferItem, pk=pk, bundle=bundle)
    form = BundleOfferItemForm(request.POST or None, instance=item)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Bundle item updated.")
            return redirect(reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk}))
        messages.error(request, "Please correct the bundle item form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Edit Bundle Item", form=form, form_title=f"Edit Bundle Item — {bundle.name}", submit_label="Save Item", cancel_url=reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def bundle_offer_item_delete(request, prefix, bundle_pk, pk):
    bundle = get_object_or_404(BundleOffer, pk=bundle_pk)
    item = get_object_or_404(BundleOfferItem, pk=pk, bundle=bundle)
    item.delete()
    messages.success(request, "Bundle item deleted.")
    return redirect(reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": bundle.pk}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def review_moderation_list(request, prefix):
    reviews = ProductReview.objects.select_related("product", "customer__user", "response_by").order_by("-created_at")
    status = request.GET.get("status", "").strip()
    if status:
        reviews = reviews.filter(status=status)
    rows = []
    for review in reviews[:200]:
        customer_label = getattr(getattr(review.customer, "user", None), "email", "") or "Guest"
        rows.append(
            {
                "detail_url": reverse("dashboard:pricing:review_moderation_detail", kwargs={"prefix": prefix, "pk": review.pk}),
                "cells": [
                    review.product.name,
                    customer_label,
                    f"{review.rating}/5",
                    review.get_status_display(),
                    "Yes" if review.is_verified_purchase else "No",
                    _fmt_datetime(review.created_at),
                ],
            }
        )
    page_obj = _paginate(request, rows, per_page=25)
    return render(request, "dashboard/pricing/ops/list.html", _ctx(prefix, "Review Moderation", columns=["Product", "Customer", "Rating", "Status", "Verified", "Created"], page_obj=page_obj, page_heading="Review Moderation", page_description="Approve, reject, feature, and respond to customer reviews that feed storefront trust and review-triggered promotions."))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def review_moderation_detail(request, prefix, pk):
    review = get_object_or_404(ProductReview.objects.select_related("product", "customer__user", "response_by"), pk=pk)
    form = ProductReviewModerationForm(request.POST or None, instance=review)
    if request.method == "POST":
        if form.is_valid():
            moderated = form.save(commit=False)
            original_status = review.status
            if moderated.status == ProductReview.Status.APPROVED and original_status != ProductReview.Status.APPROVED:
                moderated.mark_approved()
            elif moderated.status == ProductReview.Status.REJECTED and original_status != ProductReview.Status.REJECTED:
                moderated.mark_rejected(moderated.moderation_notes or "")
            if moderated.response_body and not moderated.responded_at:
                moderated.responded_at = timezone.now()
                moderated.response_by = request.user
            moderated.save()
            refresh_product_review_stats(review.product)
            messages.success(request, "Review moderation updated.")
            return redirect(reverse("dashboard:pricing:review_moderation_detail", kwargs={"prefix": prefix, "pk": review.pk}))
        messages.error(request, "Please correct the moderation form errors below.")
    return render(request, "dashboard/pricing/ops/review_detail.html", _ctx(prefix, f"Review — {review.product.name}", review=review, form=form, back_url=reverse("dashboard:pricing:review_moderation_list", kwargs={"prefix": prefix})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def pricing_segment_list(request, prefix):
    groups = CustomerGroup.objects.annotate(member_count=Count("customers", distinct=True)).order_by("sort_order", "name")
    rows = []
    for group in groups:
        rows.append(
            {
                "detail_url": reverse("dashboard:pricing:pricing_segment_detail", kwargs={"prefix": prefix, "pk": group.pk}),
                "cells": [
                    group.name,
                    group.get_group_type_display(),
                    str(group.member_count or 0),
                    str(len(group.auto_rules or {})),
                    group.slug,
                    getattr(group, "color", "#4c4c88"),
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:pricing_segment_edit", kwargs={"prefix": prefix, "pk": group.pk})),
                    _post_action("Delete", reverse("dashboard:pricing:pricing_segment_delete", kwargs={"prefix": prefix, "pk": group.pk}), tone="danger"),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(request, "dashboard/pricing/ops/list.html", _ctx(prefix, "Pricing Segments", columns=["Segment", "Type", "Members", "Rules", "Slug", "Color"], page_obj=page_obj, create_url=reverse("dashboard:pricing:pricing_segment_create", kwargs={"prefix": prefix}), create_label="Create Segment", page_heading="Pricing Segments", page_description="Manage manual and dynamic customer segments used by discount eligibility, automation targeting, and analytics.", toolbar_actions=[_post_action("Sync Dynamic Segments", reverse("dashboard:pricing:pricing_segment_sync", kwargs={"prefix": prefix}), tone="primary")]))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def pricing_segment_detail(request, prefix, pk):
    group = get_object_or_404(CustomerGroup.objects.prefetch_related("customers__user"), pk=pk)
    member_rows = []
    for customer in group.customers.select_related("user").order_by("-created_at")[:50]:
        member_rows.append(
            {
                "cells": [
                    getattr(customer.user, "email", "") or f"Customer {customer.pk}",
                    customer.status,
                    customer.tier,
                    _fmt_money(customer.total_spent),
                    str(customer.total_orders),
                ]
            }
        )
    return render(
        request,
        "dashboard/pricing/ops/detail.html",
        _ctx(
            prefix,
            f"Segment — {group.name}",
            object_title=group.name,
            object_subtitle=group.description,
            back_url=reverse("dashboard:pricing:pricing_segment_list", kwargs={"prefix": prefix}),
            edit_url=reverse("dashboard:pricing:pricing_segment_edit", kwargs={"prefix": prefix, "pk": group.pk}),
            toolbar_actions=[
                _post_action("Sync Dynamic Segments", reverse("dashboard:pricing:pricing_segment_sync", kwargs={"prefix": prefix}), tone="primary"),
                _post_action("Delete Segment", reverse("dashboard:pricing:pricing_segment_delete", kwargs={"prefix": prefix, "pk": group.pk}), tone="danger"),
            ],
            summary_cards=[
                {"label": "Type", "value": group.get_group_type_display(), "helper": group.slug},
                {"label": "Members", "value": group.customers.count(), "helper": "Current segment membership"},
                {"label": "Rules", "value": len(group.auto_rules or {}), "helper": "Auto-rule keys"},
                {"label": "Sort Order", "value": group.sort_order, "helper": "Dashboard ordering"},
            ],
            meta_rows=[
                ("Color", group.color),
                ("Description", group.description or "—"),
                ("Auto Rules", json.dumps(group.auto_rules or {}, indent=2)),
            ],
            tables=[
                {"title": "Customers", "columns": ["Customer", "Status", "Tier", "Total Spent", "Orders"], "rows": member_rows, "empty_message": "No customers currently belong to this segment."},
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def pricing_segment_create(request, prefix):
    form = PricingSegmentForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            group = form.save()
            messages.success(request, "Segment created.")
            return redirect(reverse("dashboard:pricing:pricing_segment_detail", kwargs={"prefix": prefix, "pk": group.pk}))
        messages.error(request, "Please correct the segment form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Create Segment", form=form, form_title="Create Pricing Segment", submit_label="Save Segment", cancel_url=reverse("dashboard:pricing:pricing_segment_list", kwargs={"prefix": prefix})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def pricing_segment_edit(request, prefix, pk):
    group = get_object_or_404(CustomerGroup, pk=pk)
    form = PricingSegmentForm(request.POST or None, instance=group)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Segment updated.")
            return redirect(reverse("dashboard:pricing:pricing_segment_detail", kwargs={"prefix": prefix, "pk": group.pk}))
        messages.error(request, "Please correct the segment form errors below.")
    return render(request, "dashboard/pricing/ops/form.html", _ctx(prefix, "Edit Segment", form=form, form_title="Edit Pricing Segment", submit_label="Save Segment", cancel_url=reverse("dashboard:pricing:pricing_segment_detail", kwargs={"prefix": prefix, "pk": group.pk})))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def pricing_segment_sync(request, prefix):
    result = sync_dynamic_customer_groups()
    messages.success(request, f"Dynamic segments synced. Groups refreshed: {len(result.get('groups', []))}.")
    return redirect(reverse("dashboard:pricing:pricing_segment_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def discount_experiment_delete(request, prefix, pk):
    experiment = get_object_or_404(DiscountExperiment, pk=pk)
    title = experiment.title
    experiment.delete()
    messages.success(request, f"Experiment '{title}' deleted.")
    return redirect(reverse("dashboard:pricing:discount_experiment_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def discount_experiment_variant_delete(request, prefix, experiment_pk, pk):
    experiment = get_object_or_404(DiscountExperiment, pk=experiment_pk)
    variant = get_object_or_404(DiscountExperimentVariant, pk=pk, experiment=experiment)
    label = variant.label
    variant.delete()
    messages.success(request, f"Variant '{label}' deleted.")
    return redirect(reverse("dashboard:pricing:discount_experiment_detail", kwargs={"prefix": prefix, "pk": experiment.pk}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_import_batch_error_report(request, prefix, pk):
    batch = get_object_or_404(DiscountImportBatch, pk=pk)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="discount-import-errors-{batch.pk}.csv"'
    writer = csv.writer(response)
    writer.writerow(["row_number", "preview_code", "is_valid", "errors", "normalized_data", "raw_data"])
    for row in batch.rows.order_by("row_number"):
        writer.writerow(
            [
                row.row_number,
                row.preview_code,
                "true" if row.is_valid else "false",
                " | ".join(row.validation_errors or []),
                json.dumps(row.normalized_data or {}, sort_keys=True),
                json.dumps(row.raw_data or {}, sort_keys=True),
            ]
        )
    return response


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_import_batch_rows_export(request, prefix, pk):
    batch = get_object_or_404(DiscountImportBatch, pk=pk)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="discount-import-preview-{batch.pk}.csv"'
    writer = csv.writer(response)
    writer.writerow(["row_number", "preview_code", "is_valid", "created_discount_code", "normalized_data"])
    for row in batch.rows.select_related("created_discount").order_by("row_number"):
        writer.writerow(
            [
                row.row_number,
                row.preview_code,
                "true" if row.is_valid else "false",
                row.created_discount.code if row.created_discount_id else "",
                json.dumps(row.normalized_data or {}, sort_keys=True),
            ]
        )
    return response


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def pricing_automation_rule_delete(request, prefix, pk):
    rule = get_object_or_404(PricingAutomationRule, pk=pk)
    name = rule.name
    rule.delete()
    messages.success(request, f"Automation rule '{name}' deleted.")
    return redirect(reverse("dashboard:pricing:pricing_automation_rule_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def promotion_partner_delete(request, prefix, pk):
    partner = get_object_or_404(PromotionPartner, pk=pk)
    name = partner.name
    partner.delete()
    messages.success(request, f"Promotion partner '{name}' deleted.")
    return redirect(reverse("dashboard:pricing:promotion_partner_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_link_list(request, prefix):
    links = PromotionLink.objects.select_related("discount_code", "partner").order_by("-created_at", "slug")
    target_type = (request.GET.get("target_type") or "").strip()
    partner_id = (request.GET.get("partner") or "").strip()
    discount_code_id = (request.GET.get("discount_code") or "").strip()
    bundle_id = (request.GET.get("bundle") or "").strip()
    if target_type:
        links = links.filter(target_type=target_type)
    if partner_id:
        links = links.filter(partner_id=partner_id)
    if discount_code_id:
        links = links.filter(discount_code_id=discount_code_id)
    if bundle_id:
        links = links.filter(bundle_offer_id=bundle_id)

    rows = []
    for link in links:
        rows.append(
            {
                "detail_url": reverse("dashboard:pricing:promotion_link_detail", kwargs={"prefix": prefix, "pk": link.pk}),
                "cells": [
                    link.slug,
                    link.get_target_type_display(),
                    _promotion_link_target_label(link),
                    link.landing_path or "â€”",
                    str(link.click_count),
                    _fmt_datetime(link.created_at),
                ],
                "actions": [
                    _link_action("Edit", reverse("dashboard:pricing:promotion_link_edit", kwargs={"prefix": prefix, "pk": link.pk})),
                    _post_action("Refresh QR", reverse("dashboard:pricing:promotion_link_refresh_qr", kwargs={"prefix": prefix, "pk": link.pk})),
                    _link_action("Download SVG", reverse("dashboard:pricing:promotion_link_download_qr", kwargs={"prefix": prefix, "pk": link.pk})),
                    _post_action("Delete", reverse("dashboard:pricing:promotion_link_delete", kwargs={"prefix": prefix, "pk": link.pk}), tone="danger"),
                ],
            }
        )
    page_obj = _paginate(request, rows)
    return render(
        request,
        "dashboard/pricing/ops/list.html",
        _ctx(
            prefix,
            "Promotion Links",
            columns=["Slug", "Target Type", "Target", "Landing Path", "Clicks", "Created"],
            page_obj=page_obj,
            page_heading="Promotion Links",
            page_description="Manage canonical share URLs, QR payloads, UTM settings, and click telemetry for discounts, partners, and bundles.",
            toolbar_actions=[
                _link_action("Export Links", reverse("dashboard:pricing:promotion_link_export_csv", kwargs={"prefix": prefix}), tone="primary"),
            ],
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_link_detail(request, prefix, pk):
    link = get_object_or_404(PromotionLink.objects.select_related("discount_code", "partner"), pk=pk)
    if not link.qr_svg:
        _refresh_link_qr(link, request=request)
    share_url = _promotion_link_share_url(request, link)
    target = _promotion_link_target(link)
    target_link = None
    if isinstance(target, DiscountCode):
        target_link = reverse("dashboard:pricing:discount_code_detail", kwargs={"prefix": prefix, "pk": target.pk})
    elif isinstance(target, PromotionPartner):
        target_link = reverse("dashboard:pricing:promotion_partner_detail", kwargs={"prefix": prefix, "pk": target.pk})
    elif isinstance(target, BundleOffer):
        target_link = reverse("dashboard:pricing:bundle_offer_detail", kwargs={"prefix": prefix, "pk": target.pk})
    return render(
        request,
        "dashboard/pricing/ops/promotion_link_detail.html",
        _ctx(
            prefix,
            f"Promotion Link â€” {link.slug}",
            link=link,
            share_url=share_url,
            target_label=_promotion_link_target_label(link),
            target_link=target_link,
            query_items=sorted(_promotion_link_query(link).items()),
            back_url=reverse("dashboard:pricing:promotion_link_list", kwargs={"prefix": prefix}),
            edit_url=reverse("dashboard:pricing:promotion_link_edit", kwargs={"prefix": prefix, "pk": link.pk}),
            refresh_url=reverse("dashboard:pricing:promotion_link_refresh_qr", kwargs={"prefix": prefix, "pk": link.pk}),
            download_url=reverse("dashboard:pricing:promotion_link_download_qr", kwargs={"prefix": prefix, "pk": link.pk}),
            delete_url=reverse("dashboard:pricing:promotion_link_delete", kwargs={"prefix": prefix, "pk": link.pk}),
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_link_edit(request, prefix, pk):
    link = get_object_or_404(PromotionLink, pk=pk)
    form = PromotionLinkForm(request.POST or None, instance=link)
    if request.method == "POST":
        if form.is_valid():
            link = form.save()
            _refresh_link_qr(link, request=request)
            messages.success(request, "Promotion link updated and QR refreshed.")
            return redirect(reverse("dashboard:pricing:promotion_link_detail", kwargs={"prefix": prefix, "pk": link.pk}))
        messages.error(request, "Please correct the promotion link form errors below.")
    return render(
        request,
        "dashboard/pricing/ops/form.html",
        _ctx(
            prefix,
            f"Edit Promotion Link â€” {link.slug}",
            form=form,
            form_title=f"Edit Promotion Link â€” {link.slug}",
            form_description="Adjust the canonical slug, landing path, UTM payload, and query overrides used in the generated share URL.",
            submit_label="Save Link",
            cancel_url=reverse("dashboard:pricing:promotion_link_detail", kwargs={"prefix": prefix, "pk": link.pk}),
        ),
    )


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def promotion_link_refresh_qr(request, prefix, pk):
    link = get_object_or_404(PromotionLink, pk=pk)
    _refresh_link_qr(link, request=request)
    messages.success(request, "Promotion link QR graphic refreshed.")
    return redirect(reverse("dashboard:pricing:promotion_link_detail", kwargs={"prefix": prefix, "pk": link.pk}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_link_download_qr(request, prefix, pk):
    link = get_object_or_404(PromotionLink, pk=pk)
    if not link.qr_svg:
        _refresh_link_qr(link, request=request)
    response = HttpResponse(link.qr_svg, content_type="image/svg+xml")
    response["Content-Disposition"] = f'attachment; filename="{link.slug or "promotion-link"}-qr.svg"'
    return response


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def promotion_link_delete(request, prefix, pk):
    link = get_object_or_404(PromotionLink, pk=pk)
    slug = link.slug
    link.delete()
    messages.success(request, f"Promotion link '{slug}' deleted.")
    return redirect(reverse("dashboard:pricing:promotion_link_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def promotion_link_export_csv(request, prefix):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="promotion-links.csv"'
    writer = csv.writer(response)
    writer.writerow(["slug", "target_type", "target", "landing_path", "utm_source", "utm_medium", "utm_campaign", "utm_content", "click_count"])
    for link in PromotionLink.objects.select_related("discount_code", "partner").order_by("slug"):
        writer.writerow(
            [
                link.slug,
                link.target_type,
                _promotion_link_target_label(link),
                link.landing_path,
                link.utm_source,
                link.utm_medium,
                link.utm_campaign,
                link.utm_content,
                link.click_count,
            ]
        )
    return response


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def bundle_offer_delete(request, prefix, pk):
    bundle = get_object_or_404(BundleOffer, pk=pk)
    name = bundle.name
    bundle.delete()
    messages.success(request, f"Bundle offer '{name}' deleted.")
    return redirect(reverse("dashboard:pricing:bundle_offer_list", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def pricing_segment_delete(request, prefix, pk):
    group = get_object_or_404(CustomerGroup, pk=pk)
    name = group.name
    try:
        group.delete()
        messages.success(request, f"Segment '{name}' deleted.")
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(reverse("dashboard:pricing:pricing_segment_detail", kwargs={"prefix": prefix, "pk": group.pk}))
    return redirect(reverse("dashboard:pricing:pricing_segment_list", kwargs={"prefix": prefix}))
