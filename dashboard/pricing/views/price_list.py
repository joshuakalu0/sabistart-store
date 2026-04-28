"""dashboard/pricing/views/price_list.py — PriceList, Assignment, and Entry views."""
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.sidebar_utiles import main_sidebar
from dashboard.pricing.models import PriceList, PriceListCustomerGroup, PriceListEntry
from dashboard.pricing.forms import PriceListForm, PriceListCustomerGroupForm, PriceListEntryForm

logger = logging.getLogger("pricing.views.price_list")


def _ctx(prefix, page_title, active_menu="pricing_price_lists", **extra):
    base = {"prefix": prefix, "page_title": page_title,
            "active_menu": active_menu, "sidebar": main_sidebar(prefix)}
    base.update(extra)
    return base


# ─────────────────────────────────────────────────────────────
# PRICE LIST
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def price_list_list(request, prefix):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = PriceList.objects.select_related("currency").all()
    if q:
        qs = qs.filter(name__icontains=q) | PriceList.objects.filter(code__icontains=q)
        qs = qs.distinct()
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    ctx = _ctx(prefix, "Price Lists", price_lists=qs, q=q, status=status,
               create_url=reverse("dashboard:pricing:price_list_create", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/price_list/list.html", ctx)


@login_required
@dashboard_prefix_required
def price_list_detail(request, prefix, pk):
    obj = get_object_or_404(PriceList, pk=pk)
    assignments = obj.customer_group_assignments.select_related("customer_group", "customer").all()
    entries = obj.entries.select_related("product", "variant", "category").all()[:50]
    ctx = _ctx(prefix, f"Price List — {obj.name}", price_list=obj,
               assignments=assignments, entries=entries,
               edit_url=reverse("dashboard:pricing:price_list_edit", kwargs={"prefix": prefix, "pk": pk}),
               assignments_url=reverse("dashboard:pricing:price_list_assignment_list", kwargs={"prefix": prefix, "price_list_pk": pk}),
               entries_url=reverse("dashboard:pricing:price_list_entry_list", kwargs={"prefix": prefix, "price_list_pk": pk}))
    return render(request, "dashboard/pricing/price_list/detail.html", ctx)


@login_required
@dashboard_prefix_required
def price_list_create(request, prefix):
    form = PriceListForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Price list created.")
                return redirect(reverse("dashboard:pricing:price_list_list", kwargs={"prefix": prefix}))
            except Exception as exc:
                logger.error("price_list_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, "Add Price List", form=form, is_edit=False, form_title="Add Price List",
               list_url=reverse("dashboard:pricing:price_list_list", kwargs={"prefix": prefix}))
    return render(request, "dashboard/pricing/price_list/form.html", ctx)


@login_required
@dashboard_prefix_required
def price_list_edit(request, prefix, pk):
    obj = get_object_or_404(PriceList, pk=pk)
    form = PriceListForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Price list updated.")
                return redirect(reverse("dashboard:pricing:price_list_detail", kwargs={"prefix": prefix, "pk": pk}))
            except Exception as exc:
                logger.error("price_list_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit — {obj.name}", form=form, is_edit=True, object=obj,
               form_title=f"Edit Price List — {obj.name}",
               list_url=reverse("dashboard:pricing:price_list_list", kwargs={"prefix": prefix}),
               detail_url=reverse("dashboard:pricing:price_list_detail", kwargs={"prefix": prefix, "pk": pk}))
    return render(request, "dashboard/pricing/price_list/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def price_list_delete(request, prefix, pk):
    obj = get_object_or_404(PriceList, pk=pk)
    try:
        obj.delete()
        messages.success(request, f"Price list '{obj.name}' deleted.")
    except Exception as exc:
        logger.error("price_list_delete error: %s", exc)
        messages.error(request, f"Error deleting price list: {exc}")
    return redirect(reverse("dashboard:pricing:price_list_list", kwargs={"prefix": prefix}))


# ─────────────────────────────────────────────────────────────
# PRICE LIST CUSTOMER GROUP ASSIGNMENT
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def price_list_assignment_list(request, prefix, price_list_pk):
    pl = get_object_or_404(PriceList, pk=price_list_pk)
    qs = pl.customer_group_assignments.select_related("customer_group", "customer", "assigned_by").all()
    ctx = _ctx(prefix, f"Assignments — {pl.name}", price_list=pl, assignments=qs,
               create_url=reverse("dashboard:pricing:price_list_assignment_create", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}),
               detail_url=reverse("dashboard:pricing:price_list_detail", kwargs={"prefix": prefix, "pk": price_list_pk}))
    return render(request, "dashboard/pricing/price_list_assignment/list.html", ctx)


@login_required
@dashboard_prefix_required
def price_list_assignment_create(request, prefix, price_list_pk):
    pl = get_object_or_404(PriceList, pk=price_list_pk)
    form = PriceListCustomerGroupForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save(commit=False)
                    assignment.price_list = pl
                    assignment.assigned_by = request.user
                    assignment.save()
                messages.success(request, "Assignment created.")
                return redirect(reverse("dashboard:pricing:price_list_assignment_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
            except Exception as exc:
                logger.error("price_list_assignment_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Add Assignment — {pl.name}", form=form, is_edit=False,
               price_list=pl, form_title=f"Add Assignment to {pl.name}",
               list_url=reverse("dashboard:pricing:price_list_assignment_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
    return render(request, "dashboard/pricing/price_list_assignment/form.html", ctx)


@login_required
@dashboard_prefix_required
def price_list_assignment_edit(request, prefix, price_list_pk, pk):
    pl = get_object_or_404(PriceList, pk=price_list_pk)
    obj = get_object_or_404(PriceListCustomerGroup, pk=pk, price_list=pl)
    form = PriceListCustomerGroupForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Assignment updated.")
                return redirect(reverse("dashboard:pricing:price_list_assignment_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
            except Exception as exc:
                logger.error("price_list_assignment_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Assignment — {pl.name}", form=form, is_edit=True, object=obj,
               price_list=pl, form_title="Edit Assignment",
               list_url=reverse("dashboard:pricing:price_list_assignment_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
    return render(request, "dashboard/pricing/price_list_assignment/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def price_list_assignment_delete(request, prefix, price_list_pk, pk):
    pl = get_object_or_404(PriceList, pk=price_list_pk)
    obj = get_object_or_404(PriceListCustomerGroup, pk=pk, price_list=pl)
    try:
        obj.delete()
        messages.success(request, "Assignment removed.")
    except Exception as exc:
        logger.error("price_list_assignment_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:price_list_assignment_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))


# ─────────────────────────────────────────────────────────────
# PRICE LIST ENTRY
# ─────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
def price_list_entry_list(request, prefix, price_list_pk):
    pl = get_object_or_404(PriceList, pk=price_list_pk)
    qs = pl.entries.select_related("product", "variant", "category").filter(is_active=True)
    ctx = _ctx(prefix, f"Entries — {pl.name}", price_list=pl, entries=qs,
               create_url=reverse("dashboard:pricing:price_list_entry_create", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}),
               detail_url=reverse("dashboard:pricing:price_list_detail", kwargs={"prefix": prefix, "pk": price_list_pk}))
    return render(request, "dashboard/pricing/price_list_entry/list.html", ctx)


@login_required
@dashboard_prefix_required
def price_list_entry_create(request, prefix, price_list_pk):
    pl = get_object_or_404(PriceList, pk=price_list_pk)
    form = PriceListEntryForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    entry = form.save(commit=False)
                    entry.price_list = pl
                    entry.save()
                messages.success(request, "Price entry added.")
                return redirect(reverse("dashboard:pricing:price_list_entry_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
            except Exception as exc:
                logger.error("price_list_entry_create error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Add Entry — {pl.name}", form=form, is_edit=False,
               price_list=pl, form_title=f"Add Price Entry to {pl.name}",
               list_url=reverse("dashboard:pricing:price_list_entry_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
    return render(request, "dashboard/pricing/price_list_entry/form.html", ctx)


@login_required
@dashboard_prefix_required
def price_list_entry_edit(request, prefix, price_list_pk, pk):
    pl = get_object_or_404(PriceList, pk=price_list_pk)
    obj = get_object_or_404(PriceListEntry, pk=pk, price_list=pl)
    form = PriceListEntryForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, "Price entry updated.")
                return redirect(reverse("dashboard:pricing:price_list_entry_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
            except Exception as exc:
                logger.error("price_list_entry_edit error: %s", exc)
                messages.error(request, f"Error: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    ctx = _ctx(prefix, f"Edit Entry — {pl.name}", form=form, is_edit=True, object=obj,
               price_list=pl, form_title="Edit Price Entry",
               list_url=reverse("dashboard:pricing:price_list_entry_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
    return render(request, "dashboard/pricing/price_list_entry/form.html", ctx)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def price_list_entry_delete(request, prefix, price_list_pk, pk):
    pl = get_object_or_404(PriceList, pk=price_list_pk)
    obj = get_object_or_404(PriceListEntry, pk=pk, price_list=pl)
    try:
        obj.delete()
        messages.success(request, "Price entry removed.")
    except Exception as exc:
        logger.error("price_list_entry_delete error: %s", exc)
        messages.error(request, f"Error: {exc}")
    return redirect(reverse("dashboard:pricing:price_list_entry_list", kwargs={"prefix": prefix, "price_list_pk": price_list_pk}))
