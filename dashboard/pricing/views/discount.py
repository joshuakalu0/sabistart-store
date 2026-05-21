"""dashboard/pricing/views/discount.py — DiscountCode, DiscountRule, DiscountUsage, AutomaticDiscount views."""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import require_feature
from dashboard.sidebar_utiles import main_sidebar
from dashboard.pricing.models import (
    DiscountCode, DiscountRule, DiscountUsage,
    AutomaticDiscount, AutomaticDiscountCondition, AutomaticDiscountBenefit,
    DiscountExperiment, PromotionConflictRecord,
)
from dashboard.pricing.forms import (
    DiscountCodeForm, DiscountRuleForm,
    AutomaticDiscountForm, AutomaticDiscountConditionForm, AutomaticDiscountBenefitForm,
)
from dashboard.pricing.utiles.advanced import build_promotion_link

logger = logging.getLogger("pricing.views.discount")


def _currency_symbol(code: str | None) -> str:
    symbols = {"USD": "$", "NGN": "₦", "GBP": "£", "EUR": "€", "KES": "KES", "GHS": "GHS"}
    return symbols.get((code or "USD").upper(), (code or "USD").upper())


def _decorate_discount_code(obj):
    obj.discount = obj
    obj.internal_name = obj.title
    obj.discount_type = obj.value_type
    obj.discount_value = obj.percentage_value if obj.value_type == obj.ValueType.PERCENTAGE else obj.fixed_amount
    obj.times_used = obj.usage_count
    obj.per_customer_limit = obj.usage_limit_per_customer
    obj.minimum_order_value = obj.minimum_order_amount
    obj.applies_once_per_order = obj.allocation_method == obj.AllocationMethod.ONE
    obj.get_discount_type_display = obj.get_value_type_display
    obj.get_currency_symbol = _currency_symbol(obj.currency)
    obj.currency_symbol = _currency_symbol(obj.currency)
    group_ids = obj.rules.filter(rule_type="customer_group", customer_group__isnull=False).values_list("customer_group_id", flat=True)
    try:
        from public.userauth.models import CustomerGroup

        obj.allowed_customer_groups = CustomerGroup.objects.filter(id__in=group_ids)
    except Exception:
        obj.allowed_customer_groups = []
    return obj


def _decorate_discount_rule(rule):
    rule.target_product = getattr(rule, "product", None)
    rule.target_category = getattr(rule, "category", None)
    rule.target_variant = getattr(rule, "variant", None)
    rule.is_inclusion = rule.rule_type not in {"exclude_specific_products", "exclude_sale_items"}
    rule.get_target_type_display = rule.get_rule_type_display()
    return rule


def _decorate_automatic_discount(obj):
    obj.name = obj.title
    obj.is_combinable = bool(obj.allow_stacking or obj.is_combinable_with_codes)
    obj.currency_symbol = "$"
    obj.times_configured = obj.conditions.count() + obj.benefits.count()
    return obj


def _decorate_auto_condition(condition):
    condition.target_customer_group = getattr(condition, "customer_group", None)
    condition.target_product = getattr(condition, "product", None)
    condition.target_category = None
    condition.minimum_amount = condition.amount_threshold
    condition.minimum_quantity = condition.quantity_threshold or condition.integer_threshold
    condition.condition_type_label = condition.get_condition_type_display()
    condition.get_condition_type_display = condition.condition_type_label

    if condition.condition_type == "minimum_subtotal":
        condition.condition_type = "cart_subtotal"
    elif condition.condition_type == "customer_group":
        condition.condition_type = "customer_group"
    elif condition.condition_type == "product_in_cart":
        condition.condition_type = "product_quantity"
    elif condition.condition_type == "minimum_quantity":
        condition.condition_type = "cart_quantity"
    elif condition.condition_type == "order_count_min":
        condition.condition_type = "customer_order_min"
    elif condition.condition_type == "order_count_max":
        condition.condition_type = "customer_order_max"
    return condition


def _decorate_auto_benefit(discount, benefit):
    benefit.target_product = getattr(benefit, "product", None)
    benefit.target_category = None
    benefit.max_discount_amount = getattr(discount, "max_discount_amount", None)
    benefit.get_target_type_display = benefit.get_benefit_scope_display()

    if discount.discount_method == discount.DiscountMethod.FREE_SHIPPING or benefit.benefit_scope == benefit.BenefitScope.SHIPPING:
        benefit.target_type = "free_shipping"
        benefit.discount_type = "free_shipping"
        benefit.discount_value = None
        benefit.get_discount_type_display = "Free Shipping"
    elif benefit.benefit_scope == benefit.BenefitScope.SPECIFIC_PRODUCT and benefit.product_id:
        benefit.target_type = "specific_product"
        benefit.discount_type = "percentage" if benefit.percentage_value else "fixed"
        benefit.discount_value = benefit.percentage_value or benefit.fixed_amount
        benefit.get_discount_type_display = "Percentage Off" if benefit.discount_type == "percentage" else "Fixed Amount Off"
    else:
        benefit.target_type = "order_subtotal"
        benefit.discount_type = "percentage" if (benefit.percentage_value or discount.percentage_value) else "fixed"
        benefit.discount_value = benefit.percentage_value or benefit.fixed_amount or discount.percentage_value or discount.fixed_amount
        benefit.get_discount_type_display = "Percentage Off" if benefit.discount_type == "percentage" else "Fixed Amount Off"
    return benefit


def _decorate_usage(usage):
    usage.user = getattr(getattr(usage, "customer", None), "user", None)
    usage.amount_saved = usage.discount_amount
    return usage


def _paginate(request, items, per_page=20):
    paginator = Paginator(items, per_page)
    return paginator.get_page(request.GET.get("page"))


def _ctx(prefix, page_title, active_menu="pricing_discounts", **extra):
    base = {"prefix": prefix, "page_title": page_title,
            "active_menu": active_menu, "sidebar": main_sidebar(prefix)}
    base.update(extra)
    return base


# ─────────────────────────────────────────────────────────────
# DISCOUNT CODE
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_code_list(request, prefix):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    vtype = request.GET.get("vtype", "")
    qs = DiscountCode.objects.all().prefetch_related("rules")
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(title__icontains=q))
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    if vtype:
        qs = qs.filter(value_type=vtype)
    codes = [_decorate_discount_code(obj) for obj in qs.order_by("-created_at")]
    page_obj = _paginate(request, codes, per_page=20)
    ctx = _ctx(prefix, "Discount Codes", codes=page_obj, q=q, status=status, vtype=vtype,
               create_url=reverse("dashboard:pricing:discount_code_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/discount_code/list.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_code_detail(request, prefix, pk):
    obj = get_object_or_404(DiscountCode, pk=pk)
    rules = obj.rules.all()
    usages = obj.usages.select_related("customer").order_by("-used_at")[:50]
    ctx = _ctx(prefix, f"Discount — {obj.code}", code=obj, rules=rules, usages=usages,
               edit_url=reverse("dashboard:pricing:discount_code_edit", kwargs={
                                "prefix": prefix, "pk": pk}),
               rules_url=reverse("dashboard:pricing:discount_rule_list", kwargs={
                                 "prefix": prefix, "code_pk": pk}),
               usages_url=reverse("dashboard:pricing:discount_usage_list", kwargs={"prefix": prefix, "code_pk": pk}))
    return render(request, "dashboard/pricing/discount_code/detail.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_code_create(request, prefix):
    form = DiscountCodeForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Discount code created.")
                return redirect(reverse("dashboard:pricing:discount_code_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("discount_code_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")

    ctx = _ctx(prefix, "Add Discount Code", form=form, is_edit=False, form_title="Add Discount Code",
               list_url=reverse("dashboard:pricing:discount_code_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/discount_code/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_code_edit(request, prefix, pk):
    obj = get_object_or_404(DiscountCode, pk=pk)
    form = DiscountCodeForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Discount code updated.")
                return redirect(reverse("dashboard:pricing:discount_code_detail", kwargs={"prefix": prefix, "pk": pk}))
            except Exception as exc:
                logger.error("discount_code_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit — {obj.code}", form=form, is_edit=True, object=obj,
               form_title=f"Edit Code — {obj.code}",
               list_url=reverse("dashboard:pricing:discount_code_list", kwargs={
                                "prefix": prefix}),
               detail_url=reverse("dashboard:pricing:discount_code_detail", kwargs={"prefix": prefix, "pk": pk}))
    return render(request, "dashboard/pricing/discount_code/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def discount_code_delete(request, prefix, pk):
    obj = get_object_or_404(DiscountCode, pk=pk)
    try:
        obj.delete()
        messages.success(request, f"Discount code '{obj.code}' deleted.")
    except Exception as exc:
        logger.error("discount_code_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:discount_code_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# DISCOUNT RULE (child of DiscountCode)
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_rule_list(request, prefix, code_pk):
    code = get_object_or_404(DiscountCode, pk=code_pk)
    rules = code.rules.all()
    ctx = _ctx(prefix, f"Rules — {code.code}", code=code, rules=rules,
               create_url=reverse("dashboard:pricing:discount_rule_create", kwargs={
                                  "prefix": prefix, "code_pk": code_pk}),
               detail_url=reverse("dashboard:pricing:discount_code_detail", kwargs={"prefix": prefix, "pk": code_pk}))
    return render(request, "dashboard/pricing/discount_rule/list.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_rule_create(request, prefix, code_pk):
    code = get_object_or_404(DiscountCode, pk=code_pk)
    form = DiscountRuleForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    rule = form.save(commit=False)
                    rule.discount_code = code
                    rule.save()
                messages.success(request, "Rule added.")
                return redirect(reverse("dashboard:pricing:discount_rule_list", kwargs={"prefix": prefix, "code_pk": code_pk}))
            except Exception as exc:
                logger.error("discount_rule_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Add Rule — {code.code}", form=form, is_edit=False, code=code, form_title="Add Eligibility Rule",
               list_url=reverse("dashboard:pricing:discount_rule_list", kwargs={"prefix": prefix, "code_pk": code_pk}))
    return render(request, "dashboard/pricing/discount_rule/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_rule_edit(request, prefix, code_pk, pk):
    code = get_object_or_404(DiscountCode, pk=code_pk)
    obj = get_object_or_404(DiscountRule, pk=pk, discount_code=code)
    form = DiscountRuleForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Rule updated.")
                return redirect(reverse("dashboard:pricing:discount_rule_list", kwargs={"prefix": prefix, "code_pk": code_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Rule — {code.code}", form=form, is_edit=True, code=code, object=obj, form_title="Edit Rule",
               list_url=reverse("dashboard:pricing:discount_rule_list", kwargs={"prefix": prefix, "code_pk": code_pk}))
    return render(request, "dashboard/pricing/discount_rule/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
@require_http_methods(["POST"])
def discount_rule_delete(request, prefix, code_pk, pk):
    code = get_object_or_404(DiscountCode, pk=code_pk)
    obj = get_object_or_404(DiscountRule, pk=pk, discount_code=code)
    try:
        obj.delete()
        messages.success(request, "Rule removed.")
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:discount_rule_list", kwargs={"prefix": prefix, "code_pk": code_pk}))


# ─────────────────────────────────────────────────────────────
# DISCOUNT USAGE — read-only ledger list
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_usage_list(request, prefix, code_pk):
    code = get_object_or_404(DiscountCode, pk=code_pk)
    qs = code.usages.select_related("customer").order_by("-used_at")
    ctx = _ctx(prefix, f"Usage — {code.code}", code=code, usages=qs,
               detail_url=reverse("dashboard:pricing:discount_code_detail", kwargs={"prefix": prefix, "pk": code_pk}))
    return render(request, "dashboard/pricing/discount_usage/list.html", ctx)


# ─────────────────────────────────────────────────────────────
# AUTOMATIC DISCOUNT
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def automatic_discount_list(request, prefix):
    q = request.GET.get("q", "").strip()
    qs = AutomaticDiscount.objects.all()
    if q:
        qs = qs.filter(title__icontains=q)
    status = request.GET.get("status", "")
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    ctx = _ctx(prefix, "Automatic Discounts", active_menu="pricing_auto_discounts",
               discounts=qs, q=q, status=status,
               create_url=reverse("dashboard:pricing:automatic_discount_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/automatic_discount/list.html", ctx)


@login_required
@dashboard_prefix_required
def automatic_discount_detail(request, prefix, pk):
    obj = get_object_or_404(AutomaticDiscount, pk=pk)
    conditions = obj.conditions.all()
    benefits = obj.benefits.all()
    ctx = _ctx(prefix, f"Auto Discount — {obj.title}", active_menu="pricing_auto_discounts", discount=obj,
               conditions=conditions, benefits=benefits,
               edit_url=reverse("dashboard:pricing:automatic_discount_edit", kwargs={
                                "prefix": prefix, "pk": pk}),
               conditions_url=reverse("dashboard:pricing:auto_condition_list", kwargs={
                                      "prefix": prefix, "discount_pk": pk}),
               benefits_url=reverse("dashboard:pricing:auto_benefit_list", kwargs={"prefix": prefix, "discount_pk": pk}))
    return render(request, "dashboard/pricing/automatic_discount/detail.html", ctx)


@login_required
@dashboard_prefix_required
def automatic_discount_create(request, prefix):
    form = AutomaticDiscountForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Automatic discount created.")
                return redirect(reverse("dashboard:pricing:automatic_discount_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("automatic_discount_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add Automatic Discount", active_menu="pricing_auto_discounts",
               form=form, is_edit=False, form_title="Add Automatic Discount",
               list_url=reverse("dashboard:pricing:automatic_discount_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/automatic_discount/form.html", ctx)


@login_required
@dashboard_prefix_required
def automatic_discount_edit(request, prefix, pk):
    obj = get_object_or_404(AutomaticDiscount, pk=pk)
    form = AutomaticDiscountForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Automatic discount updated.")
                return redirect(reverse("dashboard:pricing:automatic_discount_detail", kwargs={"prefix": prefix, "pk": pk}))
            except Exception as exc:
                logger.error("automatic_discount_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit — {obj.title}", active_menu="pricing_auto_discounts",
               form=form, is_edit=True, object=obj, form_title=f"Edit — {obj.title}",
               list_url=reverse("dashboard:pricing:automatic_discount_list", kwargs={
                                "prefix": prefix}),
               detail_url=reverse("dashboard:pricing:automatic_discount_detail", kwargs={"prefix": prefix, "pk": pk}))
    return render(request, "dashboard/pricing/automatic_discount/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def automatic_discount_delete(request, prefix, pk):
    obj = get_object_or_404(AutomaticDiscount, pk=pk)
    try:
        obj.delete()
        messages.success(request, f"Automatic discount '{obj.title}' deleted.")
    except Exception as exc:
        logger.error("automatic_discount_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:automatic_discount_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# AUTO DISCOUNT CONDITION (child of AutomaticDiscount)
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def auto_condition_list(request, prefix, discount_pk):
    discount = get_object_or_404(AutomaticDiscount, pk=discount_pk)
    conditions = discount.conditions.all()
    ctx = _ctx(prefix, f"Conditions — {discount.title}", active_menu="pricing_auto_discounts",
               discount=discount, conditions=conditions,
               create_url=reverse("dashboard:pricing:auto_condition_create", kwargs={
                                  "prefix": prefix, "discount_pk": discount_pk}),
               detail_url=reverse("dashboard:pricing:automatic_discount_detail", kwargs={"prefix": prefix, "pk": discount_pk}))
    return render(request, "dashboard/pricing/auto_condition/list.html", ctx)


@login_required
@dashboard_prefix_required
def auto_condition_create(request, prefix, discount_pk):
    discount = get_object_or_404(AutomaticDiscount, pk=discount_pk)
    form = AutomaticDiscountConditionForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    cond = form.save(commit=False)
                    cond.automatic_discount = discount
                    cond.save()
                messages.success(request, "Condition added.")
                return redirect(reverse("dashboard:pricing:auto_condition_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Add Condition — {discount.title}", active_menu="pricing_auto_discounts",
               form=form, is_edit=False, discount=discount, form_title="Add Condition",
               list_url=reverse("dashboard:pricing:auto_condition_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))
    return render(request, "dashboard/pricing/auto_condition/form.html", ctx)


@login_required
@dashboard_prefix_required
def auto_condition_edit(request, prefix, discount_pk, pk):
    discount = get_object_or_404(AutomaticDiscount, pk=discount_pk)
    obj = get_object_or_404(AutomaticDiscountCondition,
                            pk=pk, automatic_discount=discount)
    form = AutomaticDiscountConditionForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Condition updated.")
                return redirect(reverse("dashboard:pricing:auto_condition_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Condition — {discount.title}", active_menu="pricing_auto_discounts",
               form=form, is_edit=True, discount=discount, object=obj, form_title="Edit Condition",
               list_url=reverse("dashboard:pricing:auto_condition_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))
    return render(request, "dashboard/pricing/auto_condition/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def auto_condition_delete(request, prefix, discount_pk, pk):
    discount = get_object_or_404(AutomaticDiscount, pk=discount_pk)
    obj = get_object_or_404(AutomaticDiscountCondition,
                            pk=pk, automatic_discount=discount)
    try:
        obj.delete()
        messages.success(request, "Condition removed.")
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:auto_condition_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))


# ─────────────────────────────────────────────────────────────
# AUTO DISCOUNT BENEFIT (child of AutomaticDiscount)
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def auto_benefit_list(request, prefix, discount_pk):
    discount = get_object_or_404(AutomaticDiscount, pk=discount_pk)
    benefits = discount.benefits.all()
    ctx = _ctx(prefix, f"Benefits — {discount.title}", active_menu="pricing_auto_discounts",
               discount=discount, benefits=benefits,
               create_url=reverse("dashboard:pricing:auto_benefit_create", kwargs={
                                  "prefix": prefix, "discount_pk": discount_pk}),
               detail_url=reverse("dashboard:pricing:automatic_discount_detail", kwargs={"prefix": prefix, "pk": discount_pk}))
    return render(request, "dashboard/pricing/auto_benefit/list.html", ctx)


@login_required
@dashboard_prefix_required
def auto_benefit_create(request, prefix, discount_pk):
    discount = get_object_or_404(AutomaticDiscount, pk=discount_pk)
    form = AutomaticDiscountBenefitForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    benefit = form.save(commit=False)
                    benefit.automatic_discount = discount
                    benefit.save()
                messages.success(request, "Benefit added.")
                return redirect(reverse("dashboard:pricing:auto_benefit_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Add Benefit — {discount.title}", active_menu="pricing_auto_discounts",
               form=form, is_edit=False, discount=discount, form_title="Add Benefit",
               list_url=reverse("dashboard:pricing:auto_benefit_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))
    return render(request, "dashboard/pricing/auto_benefit/form.html", ctx)


@login_required
@dashboard_prefix_required
def auto_benefit_edit(request, prefix, discount_pk, pk):
    discount = get_object_or_404(AutomaticDiscount, pk=discount_pk)
    obj = get_object_or_404(AutomaticDiscountBenefit,
                            pk=pk, automatic_discount=discount)
    form = AutomaticDiscountBenefitForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Benefit updated.")
                return redirect(reverse("dashboard:pricing:auto_benefit_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Benefit — {discount.title}", active_menu="pricing_auto_discounts",
               form=form, is_edit=True, discount=discount, object=obj, form_title="Edit Benefit",
               list_url=reverse("dashboard:pricing:auto_benefit_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))
    return render(request, "dashboard/pricing/auto_benefit/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def auto_benefit_delete(request, prefix, discount_pk, pk):
    discount = get_object_or_404(AutomaticDiscount, pk=discount_pk)
    obj = get_object_or_404(AutomaticDiscountBenefit,
                            pk=pk, automatic_discount=discount)
    try:
        obj.delete()
        messages.success(request, "Benefit removed.")
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:auto_benefit_list", kwargs={"prefix": prefix, "discount_pk": discount_pk}))


# ---------------------------------------------------------------------
# UI compatibility overrides
# ---------------------------------------------------------------------

@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_code_detail(request, prefix, pk):
    obj = _decorate_discount_code(get_object_or_404(DiscountCode, pk=pk))
    rules = [_decorate_discount_rule(rule) for rule in obj.rules.all()]
    usages = [_decorate_usage(usage) for usage in obj.usages.select_related("customer").order_by("-used_at")[:50]]
    share_link = build_promotion_link(discount_code=obj)
    experiments = DiscountExperiment.objects.filter(source_discount=obj).select_related("winner_variant__discount_code").order_by("-created_at")[:5]
    conflicts = PromotionConflictRecord.objects.filter(
        Q(left_discount_code=obj) | Q(right_discount_code=obj)
    ).order_by("-created_at")[:5]
    ctx = _ctx(
        prefix,
        f"Discount - {obj.code}",
        code=obj,
        discount=obj,
        rules=rules,
        usages=usages,
        share_link=share_link,
        share_link_detail_url=reverse("dashboard:pricing:promotion_link_detail", kwargs={"prefix": prefix, "pk": share_link.pk}),
        experiments=experiments,
        conflicts=conflicts,
        edit_url=reverse("dashboard:pricing:discount_code_edit", kwargs={"prefix": prefix, "pk": pk}),
        rules_url=reverse("dashboard:pricing:discount_rule_list", kwargs={"prefix": prefix, "code_pk": pk}),
        usages_url=reverse("dashboard:pricing:discount_usage_list", kwargs={"prefix": prefix, "code_pk": pk}),
    )
    return render(request, "dashboard/pricing/discount_code/detail.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_rule_list(request, prefix, code_pk):
    code = _decorate_discount_code(get_object_or_404(DiscountCode, pk=code_pk))
    rules = [_decorate_discount_rule(rule) for rule in code.rules.all()]
    ctx = _ctx(
        prefix,
        f"Rules - {code.code}",
        code=code,
        discount=code,
        rules=rules,
        create_url=reverse("dashboard:pricing:discount_rule_create", kwargs={"prefix": prefix, "code_pk": code_pk}),
        detail_url=reverse("dashboard:pricing:discount_code_detail", kwargs={"prefix": prefix, "pk": code_pk}),
    )
    return render(request, "dashboard/pricing/discount_rule/list.html", ctx)


@login_required
@dashboard_prefix_required
@require_feature("discount_codes")
def discount_usage_list(request, prefix, code_pk):
    code = _decorate_discount_code(get_object_or_404(DiscountCode, pk=code_pk))
    usages = [_decorate_usage(usage) for usage in code.usages.select_related("customer").order_by("-used_at")]
    page_obj = _paginate(request, usages, per_page=25)
    ctx = _ctx(
        prefix,
        f"Usage - {code.code}",
        code=code,
        discount=code,
        usages=page_obj,
        detail_url=reverse("dashboard:pricing:discount_code_detail", kwargs={"prefix": prefix, "pk": code_pk}),
    )
    return render(request, "dashboard/pricing/discount_usage/list.html", ctx)


@login_required
@dashboard_prefix_required
def automatic_discount_list(request, prefix):
    q = request.GET.get("q", "").strip()
    qs = AutomaticDiscount.objects.all().prefetch_related("conditions", "benefits")
    if q:
        qs = qs.filter(title__icontains=q)
    status = request.GET.get("status", "")
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    discounts = [_decorate_automatic_discount(obj) for obj in qs.order_by("-priority", "-created_at")]
    page_obj = _paginate(request, discounts, per_page=20)
    ctx = _ctx(
        prefix,
        "Automatic Discounts",
        active_menu="pricing_auto_discounts",
        discounts=page_obj,
        q=q,
        status=status,
        create_url=reverse("dashboard:pricing:automatic_discount_create", kwargs={"prefix": prefix}),
    )
    return render(request, "dashboard/pricing/automatic_discount/list.html", ctx)


@login_required
@dashboard_prefix_required
def automatic_discount_detail(request, prefix, pk):
    discount = _decorate_automatic_discount(get_object_or_404(AutomaticDiscount, pk=pk))
    conditions = [_decorate_auto_condition(condition) for condition in discount.conditions.all()]
    benefits = [_decorate_auto_benefit(discount, benefit) for benefit in discount.benefits.all()]
    conflicts = PromotionConflictRecord.objects.filter(
        Q(left_automatic_discount=discount) | Q(right_automatic_discount=discount)
    ).order_by("-created_at")[:5]
    ctx = _ctx(
        prefix,
        f"Auto Discount - {discount.title}",
        active_menu="pricing_auto_discounts",
        discount=discount,
        conditions=conditions,
        benefits=benefits,
        conflicts=conflicts,
        edit_url=reverse("dashboard:pricing:automatic_discount_edit", kwargs={"prefix": prefix, "pk": pk}),
        conditions_url=reverse("dashboard:pricing:auto_condition_list", kwargs={"prefix": prefix, "discount_pk": pk}),
        benefits_url=reverse("dashboard:pricing:auto_benefit_list", kwargs={"prefix": prefix, "discount_pk": pk}),
    )
    return render(request, "dashboard/pricing/automatic_discount/detail.html", ctx)


@login_required
@dashboard_prefix_required
def auto_condition_list(request, prefix, discount_pk):
    discount = _decorate_automatic_discount(get_object_or_404(AutomaticDiscount, pk=discount_pk))
    conditions = [_decorate_auto_condition(condition) for condition in discount.conditions.all()]
    ctx = _ctx(
        prefix,
        f"Conditions - {discount.title}",
        active_menu="pricing_auto_discounts",
        discount=discount,
        conditions=conditions,
        create_url=reverse("dashboard:pricing:auto_condition_create", kwargs={"prefix": prefix, "discount_pk": discount_pk}),
        detail_url=reverse("dashboard:pricing:automatic_discount_detail", kwargs={"prefix": prefix, "pk": discount_pk}),
    )
    return render(request, "dashboard/pricing/auto_condition/list.html", ctx)


@login_required
@dashboard_prefix_required
def auto_benefit_list(request, prefix, discount_pk):
    discount = _decorate_automatic_discount(get_object_or_404(AutomaticDiscount, pk=discount_pk))
    benefits = [_decorate_auto_benefit(discount, benefit) for benefit in discount.benefits.all()]
    ctx = _ctx(
        prefix,
        f"Benefits - {discount.title}",
        active_menu="pricing_auto_discounts",
        discount=discount,
        benefits=benefits,
        create_url=reverse("dashboard:pricing:auto_benefit_create", kwargs={"prefix": prefix, "discount_pk": discount_pk}),
        detail_url=reverse("dashboard:pricing:automatic_discount_detail", kwargs={"prefix": prefix, "pk": discount_pk}),
    )
    return render(request, "dashboard/pricing/auto_benefit/list.html", ctx)
