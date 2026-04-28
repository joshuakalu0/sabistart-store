"""dashboard/pricing/views/discount.py — DiscountCode, DiscountRule, DiscountUsage, AutomaticDiscount views."""
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import require_feature
from dashboard.sidebar_utiles import main_sidebar
from dashboard.pricing.models import (
    DiscountCode, DiscountRule, DiscountUsage,
    AutomaticDiscount, AutomaticDiscountCondition, AutomaticDiscountBenefit,
)
from dashboard.pricing.forms import (
    DiscountCodeForm, DiscountRuleForm,
    AutomaticDiscountForm, AutomaticDiscountConditionForm, AutomaticDiscountBenefitForm,
)

logger = logging.getLogger("pricing.views.discount")


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
    qs = DiscountCode.objects.all()
    if q:
        qs = qs.filter(code__icontains=q) | DiscountCode.objects.filter(
            title__icontains=q)
        qs = qs.distinct()
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    if vtype:
        qs = qs.filter(value_type=vtype)
    ctx = _ctx(prefix, "Discount Codes", codes=qs, q=q, status=status, vtype=vtype,
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
