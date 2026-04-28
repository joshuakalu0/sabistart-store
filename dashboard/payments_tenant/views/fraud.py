import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from dashboard.decorators import dashboard_prefix_required
from dashboard.payments_tenant.forms import TenantBlocklistEntryForm, TenantFraudRuleForm
from dashboard.payments_tenant.models import BlocklistEntry, FraudAssessment, FraudRule
from dashboard.payments_tenant.view_utils import build_page_context, get_payment_profile

logger = logging.getLogger("dashboard.payments_tenant.views.fraud")


@login_required
@dashboard_prefix_required
def fraud_rule_list(request, prefix):
    profile = get_payment_profile(request)
    qs = FraudRule.objects.filter(payment_profile=profile).order_by("-priority", "name")

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    if q:
        qs = qs.filter(name__icontains=q)
    if status_filter == "active":
        qs = qs.filter(is_active=True)
    elif status_filter == "inactive":
        qs = qs.filter(is_active=False)

    rules = Paginator(qs, 25).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/fraud_rule/list.html",
        build_page_context(
            prefix,
            "Fraud Rules",
            "payments_fraud",
            rules=rules,
            q=q,
            status_filter=status_filter,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def fraud_rule_create(request, prefix):
    profile = get_payment_profile(request)
    if request.method == "POST":
        form = TenantFraudRuleForm(request.POST)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.payment_profile = profile
            rule.save()
            messages.success(request, f"Fraud rule '{rule.name}' created.")
            return redirect("dashboard:payments_tenant:fraud_rule_list", prefix=prefix)
    else:
        form = TenantFraudRuleForm()

    return render(
        request,
        "dashboard/payments_tenant/fraud_rule/form.html",
        build_page_context(
            prefix,
            "New Fraud Rule",
            "payments_fraud",
            form_title="Add Fraud Rule",
            form=form,
            is_edit=False,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def fraud_rule_edit(request, prefix, pk):
    profile = get_payment_profile(request)
    rule = get_object_or_404(FraudRule, pk=pk, payment_profile=profile)
    if request.method == "POST":
        form = TenantFraudRuleForm(request.POST, instance=rule)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.payment_profile = profile
            updated.save()
            messages.success(request, f"Fraud rule '{rule.name}' updated.")
            return redirect("dashboard:payments_tenant:fraud_rule_list", prefix=prefix)
    else:
        form = TenantFraudRuleForm(instance=rule)

    return render(
        request,
        "dashboard/payments_tenant/fraud_rule/form.html",
        build_page_context(
            prefix,
            f"Edit Rule - {rule.name}",
            "payments_fraud",
            form_title=f"Edit Fraud Rule - {rule.name}",
            form=form,
            object=rule,
            is_edit=True,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def fraud_rule_delete(request, prefix, pk):
    if request.method != "POST":
        return redirect("dashboard:payments_tenant:fraud_rule_list", prefix=prefix)

    profile = get_payment_profile(request)
    rule = get_object_or_404(FraudRule, pk=pk, payment_profile=profile)
    name = rule.name
    rule.delete()
    messages.success(request, f"Fraud rule '{name}' deleted.")
    return redirect("dashboard:payments_tenant:fraud_rule_list", prefix=prefix)


@login_required
@dashboard_prefix_required
def blocklist_list(request, prefix):
    profile = get_payment_profile(request)
    qs = BlocklistEntry.objects.filter(payment_profile=profile, is_platform_wide=False).order_by("-created_at")

    q = request.GET.get("q", "").strip()
    type_filter = request.GET.get("entry_type", "").strip()
    if q:
        qs = qs.filter(value__icontains=q)
    if type_filter:
        qs = qs.filter(entry_type=type_filter)

    entries = Paginator(qs, 25).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/blocklist/list.html",
        build_page_context(
            prefix,
            "Blocklist",
            "payments_fraud",
            entries=entries,
            q=q,
            type_filter=type_filter,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def blocklist_create(request, prefix):
    profile = get_payment_profile(request)
    if request.method == "POST":
        form = TenantBlocklistEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.payment_profile = profile
            entry.is_platform_wide = False
            entry.added_by = request.user
            entry.save()
            messages.success(request, "Blocklist entry added.")
            return redirect("dashboard:payments_tenant:blocklist_list", prefix=prefix)
    else:
        form = TenantBlocklistEntryForm()

    return render(
        request,
        "dashboard/payments_tenant/blocklist/form.html",
        build_page_context(
            prefix,
            "Add to Blocklist",
            "payments_fraud",
            form_title="Add Blocklist Entry",
            form=form,
            is_edit=False,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def blocklist_delete(request, prefix, pk):
    if request.method != "POST":
        return redirect("dashboard:payments_tenant:blocklist_list", prefix=prefix)

    profile = get_payment_profile(request)
    entry = get_object_or_404(BlocklistEntry, pk=pk, payment_profile=profile, is_platform_wide=False)
    entry.delete()
    messages.success(request, "Blocklist entry removed.")
    return redirect("dashboard:payments_tenant:blocklist_list", prefix=prefix)


@login_required
@dashboard_prefix_required
def fraud_assessment_list(request, prefix):
    profile = get_payment_profile(request)
    qs = FraudAssessment.objects.filter(payment_profile=profile).order_by("-created_at")

    decision_filter = request.GET.get("decision", "").strip()
    min_score = request.GET.get("min_score", "").strip()
    if decision_filter:
        qs = qs.filter(decision=decision_filter)
    if min_score:
        try:
            qs = qs.filter(risk_score__gte=int(min_score))
        except ValueError:
            pass

    assessments = Paginator(qs, 30).get_page(request.GET.get("page", 1))
    return render(
        request,
        "dashboard/payments_tenant/fraud_assessment/list.html",
        build_page_context(
            prefix,
            "Fraud Assessments",
            "payments_fraud",
            assessments=assessments,
            decision_filter=decision_filter,
            min_score=min_score,
            decision_choices=FraudAssessment.Decision.choices,
            profile=profile,
        ),
    )
