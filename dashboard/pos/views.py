from __future__ import annotations

from functools import wraps
import json
import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_GET, require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import require_feature
from dashboard.sidebar_utiles import main_sidebar
from dashboard.analytics.services import build_pos_dashboard_bundle, bundle_to_json, parse_analytics_window
from public.userauth.models.tenant_user import TenantUser

from .forms import POSPlaceForm, POSProductForm, POSRegisterForm, POSSessionCloseForm, POSSessionOpenForm
from .models import (
    InventoryAdjustment,
    POSCart,
    POSCartItem,
    POSDiscount,
    POSSession,
    POSTerminal,
    POSTransaction,
    Store,
    StoreInventory,
)
from .services import (
    active_discount_queryset,
    active_inventory_queryset,
    active_product_queryset,
    active_store_queryset,
    adjust_inventory as adjust_inventory_service,
    add_item_to_cart,
    build_receipt_context,
    checkout_cart,
    close_register_session,
    create_quick_pos_product,
    create_sale_transaction,
    get_cart_context,
    get_open_session,
    get_or_create_active_cart,
    get_or_create_default_register,
    get_pos_schema_issues,
    get_pos_schema_setup_command,
    hold_cart,
    open_register_session,
    refund_transaction,
    remove_cart_item,
    resume_cart,
    search_store_products,
    sync_catalog_bridge,
    sync_offline_transaction,
    to_money,
    toggle_product_status,
    update_cart_item_quantity,
    update_quick_pos_product,
    void_cart,
)


PAYMENT_METHOD_OPTIONS = [
    ("cash", "Cash"),
    ("bank_transfer", "Bank Transfer"),
    ("card_terminal", "POS Terminal / Card"),
    ("mobile_money", "Mobile Money"),
    ("custom", "Custom Payment"),
    ("split", "Split Payment"),
]


def _render_pos_schema_required(request, prefix, *, json_mode: bool = False):
    issues = get_pos_schema_issues()
    if not issues:
        return None
    setup_command = get_pos_schema_setup_command()
    schema_name = getattr(connection, "schema_name", "tenant_schema")
    message = (
        "POS setup is incomplete for this tenant schema. "
        f"Run `{setup_command}` to apply the missing POS migrations for `{schema_name}`."
    )
    if json_mode:
        return JsonResponse(
            {
                "success": False,
                "schema_setup_required": True,
                "error": message,
                "schema_name": schema_name,
                "setup_command": setup_command,
                "issues": issues,
            },
            status=503,
        )
    context = _ctx(
        prefix,
        "POS Setup Required",
        "pos_dashboard",
        pos_schema_issues=issues,
        pos_setup_command=setup_command,
        pos_schema_name=schema_name,
        pos_setup_message=message,
    )
    return render(request, "dashboard/pos/schema_setup_required.html", context, status=200)


def require_pos_schema_ready(*, json_mode: bool = False):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            prefix = kwargs.get("prefix", "")
            setup_response = _render_pos_schema_required(request, prefix, json_mode=json_mode)
            if setup_response is not None:
                return setup_response
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def _ctx(prefix, page_title, active_menu, **extra):
    base = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix, active_menu),
    }
    base.update(extra)
    return base


def _pos_url(name: str, *, prefix: str, query: dict | None = None) -> str:
    url = reverse(name, kwargs={"prefix": prefix})
    clean_query = {key: value for key, value in (query or {}).items() if value not in (None, "", [])}
    if clean_query:
        url = f"{url}?{urlencode(clean_query)}"
    return url


def _json_payload(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body)
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid JSON payload.") from exc


def _form_error_message(form):
    for field_name, errors in form.errors.items():
        if errors:
            label = form.fields[field_name].label if field_name in form.fields else "Form"
            return f"{label}: {errors[0]}"
    return "Please correct the form errors."


def _store_options():
    return active_store_queryset().order_by("name")


def _current_store(request):
    query_store_id = request.GET.get("store") or request.POST.get("store_id")
    if query_store_id:
        store = active_store_queryset().filter(pk=query_store_id).first()
        if store:
            request.session["pos_store_id"] = str(store.id)
            return store
    session_store_id = request.session.get("pos_store_id")
    if session_store_id:
        store = active_store_queryset().filter(pk=session_store_id).first()
        if store:
            return store
    store = active_store_queryset().order_by("name").first()
    if store:
        request.session["pos_store_id"] = str(store.id)
    return store


def _current_register(request, store: Store | None):
    if store is None:
        return None
    query_register_id = request.GET.get("register") or request.POST.get("register_id")
    if query_register_id:
        register = POSTerminal.objects.filter(store=store, pk=query_register_id, is_active=True, is_deleted=False).first()
        if register:
            request.session["pos_register_id"] = str(register.id)
            return register
    session_register_id = request.session.get("pos_register_id")
    if session_register_id:
        register = POSTerminal.objects.filter(store=store, pk=session_register_id, is_active=True, is_deleted=False).first()
        if register:
            return register
    register = POSTerminal.objects.filter(store=store, is_active=True, is_deleted=False).order_by("name").first()
    if register:
        request.session["pos_register_id"] = str(register.id)
    return register


def _current_session(request, store: Store | None, register: POSTerminal | None):
    if store is None or register is None or not isinstance(request.user, TenantUser):
        return None
    return get_open_session(cashier=request.user, store=store, terminal=register)


def _require_place(request, prefix):
    store = _current_store(request)
    if store is None:
        messages.info(request, "Create a POS place first.")
        return None, redirect(_pos_url("dashboard:pos:stores", prefix=prefix))
    return store, None


def _require_register_and_session(request, prefix):
    store = _current_store(request)
    if store is None:
        return None, None, None, redirect(_pos_url("dashboard:pos:stores", prefix=prefix))
    register = _current_register(request, store)
    if register is None:
        messages.info(request, "Create a register for this POS place first.")
        return store, None, None, redirect(
            _pos_url("dashboard:pos:stores", prefix=prefix, query={"store": store.id})
        )
    session = _current_session(request, store, register)
    if session is None:
        messages.info(request, "Open a register session before using checkout.")
        return store, register, None, redirect(
            _pos_url(
                "dashboard:pos:sessions",
                prefix=prefix,
                query={"store": store.id, "register": register.id},
            )
        )
    return store, register, session, None


def _payment_rows_from_payload(payload: dict, total_amount: Decimal):
    payment_method = payload.get("payment_method", "cash")
    split_payments = payload.get("payments") or []
    if payment_method == "split" and split_payments:
        rows = []
        for row in split_payments:
            rows.append(
                {
                    "payment_method": row.get("payment_method", "cash"),
                    "amount": row.get("amount", "0.00"),
                    "reference_number": row.get("reference_number", ""),
                    "bank_name": row.get("bank_name", ""),
                    "terminal_reference": row.get("terminal_reference", ""),
                    "custom_payment_label": row.get("custom_payment_label", ""),
                    "amount_received": row.get("amount_received"),
                    "balance_returned": row.get("balance_returned"),
                }
            )
        return rows
    return [
        {
            "payment_method": payment_method,
            "amount": str(total_amount),
            "reference_number": payload.get("payment_reference", ""),
            "bank_name": payload.get("bank_name", ""),
            "terminal_reference": payload.get("terminal_reference", ""),
            "custom_payment_label": payload.get("custom_payment_label", ""),
            "amount_received": payload.get("amount_received", str(total_amount) if payment_method == "cash" else None),
            "balance_returned": payload.get("balance_returned"),
        }
    ]


def _estimate_sale_total(store: Store, items_data: list[dict]) -> Decimal:
    total_amount = Decimal("0.00")
    for item in items_data:
        inventory = (
            StoreInventory.objects.select_related(
                "product",
                "catalog_item",
                "catalog_item__product",
                "catalog_item__variant",
            )
            .get(pk=item.get("inventory_id"), store=store, is_deleted=False)
        )
        quantity = Decimal(str(item.get("quantity", 0)))
        if quantity <= 0:
            continue
        unit_price = to_money(inventory.effective_selling_price)
        line_subtotal = to_money(unit_price * quantity)
        item_discount = to_money(item.get("discount_amount"))
        applicable_tax_rate = Decimal("0.0000")
        if inventory.is_taxable:
            applicable_tax_rate = (
                inventory.product.tax_rate
                if inventory.product is not None and inventory.product.tax_rate is not None
                else store.tax_rate
            ) or Decimal("0.0000")
        line_tax = to_money((line_subtotal - item_discount) * applicable_tax_rate)
        total_amount += to_money(line_subtotal - item_discount + line_tax)
    return to_money(total_amount)


def _render_receipt_response(request, template_name, context):
    if request.GET.get("format") != "pdf":
        return render(request, template_name, context)
    try:
        from xhtml2pdf import pisa
    except Exception:
        return render(request, template_name, {**context, "pdf_unavailable": True})
    html = render_to_string(template_name, context, request=request)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{context["transaction"].transaction_number}.pdf"'
    pisa.CreatePDF(html, dest=response)
    return response


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_feature("max_pos_locations")
def pos_dashboard(request, prefix):
    selected_store = _current_store(request)
    if selected_store is None:
        messages.info(request, "Create a POS place first before using the dashboard.")
        return redirect(reverse("dashboard:pos:stores", kwargs={"prefix": prefix}))
    selected_register = _current_register(request, selected_store)
    active_session = _current_session(request, selected_store, selected_register)

    transactions = (
        POSTransaction.objects.filter(is_deleted=False, status="completed", store=selected_store)
        .select_related("store", "cashier", "terminal", "session")
        .prefetch_related("payments", "items")
        .order_by("-created_at")
    )
    inventory_qs = active_inventory_queryset().select_related(
        "store", "product", "catalog_item",
        "catalog_item__product", "catalog_item__variant",
    ).filter(store=selected_store)

    summary = {
        "total_items": inventory_qs.count(),
        "low_stock_count": inventory_qs.filter(quantity__gt=0, quantity__lte=F("low_stock_threshold")).count(),
        "out_of_stock_count": inventory_qs.filter(quantity__lte=0).count(),
    }
    today_sales = transactions.filter(created_at__date=timezone.localdate()).aggregate(total=Sum("total_amount"))["total"] or 0
    today_transactions = transactions.filter(created_at__date=timezone.localdate()).count()
    products_sold = transactions.aggregate(total=Sum("items__quantity"))["total"] or 0
    payment_breakdown = list(
        transactions.values("payments__payment_method")
        .annotate(total=Sum("payments__amount"), count=Count("payments__id"))
        .order_by("-total")
    )
    cashier_activity = list(
        transactions.values("cashier__first_name", "cashier__last_name")
        .annotate(total_sales=Sum("total_amount"), transaction_count=Count("id"))
        .order_by("-total_sales")[:5]
    )

    context = _ctx(
        prefix,
        "POS Dashboard",
        "pos_dashboard",
        selected_store=selected_store,
        selected_register=selected_register,
        active_session=active_session,
        available_stores=_store_options(),
        selected_store_tax_percent=float(selected_store.tax_rate or 0) * 100,
        recent_transactions=transactions[:8],
        inventory_summary=summary,
        today_sales=today_sales,
        today_transactions=today_transactions,
        products_sold=products_sold,
        payment_breakdown=payment_breakdown,
        cashier_activity=cashier_activity,
        create_transaction_url=reverse("dashboard:pos:create_transaction", kwargs={"prefix": prefix}),
        search_products_url=reverse("dashboard:pos:search_products", kwargs={"prefix": prefix}),
        pos_analytics_bundle=build_pos_dashboard_bundle(parse_analytics_window({"period": "7d"}), selected_store=selected_store),
    )
    context["pos_analytics_bundle_json"] = bundle_to_json(context["pos_analytics_bundle"])
    return render(request, "dashboard/pos/dashboard.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_feature("max_pos_locations")
def stores(request, prefix):
    stores = _store_options().annotate(
        register_count=Count("terminals", filter=Q(terminals__is_deleted=False), distinct=True),
        inventory_count=Count("inventory", filter=Q(inventory__is_deleted=False), distinct=True),
        open_session_count=Count(
            "sessions",
            filter=Q(sessions__is_deleted=False, sessions__status="open"),
            distinct=True,
        ),
    )
    editing_store = None
    selected_store = _current_store(request)
    if request.GET.get("edit"):
        editing_store = get_object_or_404(active_store_queryset(), pk=request.GET.get("edit"))
    store_form = POSPlaceForm(request.POST or None, instance=editing_store)
    register_form = POSRegisterForm(request.POST or None)
    if selected_store:
        register_form.fields["store"].initial = selected_store
        register_form.fields["store"].queryset = stores
    if request.method == "POST":
        action = request.POST.get("action", "save_store")
        try:
            if action == "save_store":
                if not store_form.is_valid():
                    raise ValidationError(_form_error_message(store_form))
                store = store_form.save(commit=False)
                store.manager = store.manager or (request.user if isinstance(request.user, TenantUser) else None)
                store.is_active = store.status == "active"
                if not store.pk:
                    store.created_by = request.user
                store.updated_by = request.user
                store.save()
                request.session["pos_store_id"] = str(store.id)
                messages.success(request, "POS place saved.")
                return redirect(_pos_url("dashboard:pos:stores", prefix=prefix, query={"store": store.id}))
            if action == "save_register":
                if not register_form.is_valid():
                    raise ValidationError(_form_error_message(register_form))
                register = register_form.save(commit=False)
                if not register.pk:
                    register.created_by = request.user
                register.updated_by = request.user
                register.save()
                request.session["pos_register_id"] = str(register.id)
                messages.success(request, "POS register saved.")
                return redirect(
                    _pos_url("dashboard:pos:stores", prefix=prefix, query={"store": register.store_id})
                )
        except ValidationError as exc:
            messages.error(request, exc.message)
    registers = POSTerminal.objects.filter(store=selected_store, is_deleted=False).order_by("name") if selected_store else POSTerminal.objects.none()
    context = _ctx(
        prefix,
        "POS Places",
        "pos_places",
        stores=stores,
        selected_store=selected_store,
        registers=registers,
        store_form=store_form,
        register_form=register_form,
        editing_store=editing_store,
    )
    return render(request, "dashboard/pos/stores.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_feature("max_pos_locations")
def sessions(request, prefix):
    selected_store, redirect_response = _require_place(request, prefix)
    if redirect_response:
        return redirect_response
    selected_register = _current_register(request, selected_store)
    if selected_register is None:
        messages.info(request, "Create a register first before opening a session.")
        return redirect(_pos_url("dashboard:pos:stores", prefix=prefix, query={"store": selected_store.id}))
    active_session = _current_session(request, selected_store, selected_register)
    open_form = POSSessionOpenForm(request.POST or None, terminals=POSTerminal.objects.filter(store=selected_store, is_active=True, is_deleted=False))
    close_form = POSSessionCloseForm(request.POST or None)
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "open_session":
                if not open_form.is_valid():
                    raise ValidationError(_form_error_message(open_form))
                selected_register = open_form.cleaned_data["terminal"]
                request.session["pos_register_id"] = str(selected_register.id)
                open_register_session(
                    cashier=request.user,
                    store=selected_store,
                    terminal=selected_register,
                    opening_cash=open_form.cleaned_data["opening_cash"],
                    notes=open_form.cleaned_data["notes"],
                )
                messages.success(request, "Register session opened.")
                return redirect(
                    _pos_url(
                        "dashboard:pos:sessions",
                        prefix=prefix,
                        query={"store": selected_store.id, "register": selected_register.id},
                    )
                )
            if action == "close_session":
                if active_session is None:
                    raise ValidationError("There is no active session to close.")
                if not close_form.is_valid():
                    raise ValidationError(_form_error_message(close_form))
                close_register_session(
                    session=active_session,
                    closing_cash=close_form.cleaned_data["closing_cash"],
                    notes=close_form.cleaned_data["notes"],
                    user=request.user,
                )
                messages.success(request, "Register session closed.")
                return redirect(
                    _pos_url(
                        "dashboard:pos:sessions",
                        prefix=prefix,
                        query={"store": selected_store.id, "register": selected_register.id},
                    )
                )
        except ValidationError as exc:
            messages.error(request, exc.message)
    recent_sessions = (
        POSSession.objects.filter(store=selected_store, is_deleted=False)
        .select_related("terminal", "cashier")
        .annotate(
            transaction_count=Count(
                "transactions",
                filter=Q(transactions__is_deleted=False, transactions__status="completed"),
                distinct=True,
            ),
            sales_total=Sum(
                "transactions__total_amount",
                filter=Q(transactions__is_deleted=False, transactions__status="completed"),
            ),
            cash_total=Sum(
                "transactions__payments__amount",
                filter=Q(
                    transactions__is_deleted=False,
                    transactions__status="completed",
                    transactions__payments__payment_method="cash",
                ),
            ),
        )
        .order_by("-opened_at")[:20]
    )
    active_session_totals = None
    if active_session is not None:
        active_totals = active_session.transactions.filter(is_deleted=False, status="completed").aggregate(
            total_sales=Sum("total_amount"),
            transaction_count=Count("id"),
        )
        cash_total = (
            active_session.transactions.filter(is_deleted=False, status="completed", payments__payment_method="cash")
            .aggregate(total=Sum("payments__amount"))
            .get("total")
            or 0
        )
        active_session_totals = {
            "total_sales": active_totals.get("total_sales") or 0,
            "transaction_count": active_totals.get("transaction_count") or 0,
            "cash_total": cash_total,
            "expected_cash": (active_session.opening_cash or Decimal("0.00")) + Decimal(str(cash_total or 0)),
            "non_cash_total": (active_totals.get("total_sales") or 0) - Decimal(str(cash_total or 0)),
        }
    context = _ctx(
        prefix,
        "Register Sessions",
        "pos_sessions",
        selected_store=selected_store,
        selected_register=selected_register,
        active_session=active_session,
        active_session_totals=active_session_totals,
        open_form=open_form,
        close_form=close_form,
        recent_sessions=recent_sessions,
    )
    return render(request, "dashboard/pos/sessions.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_feature("max_pos_locations")
@require_http_methods(["POST"])
def create_transaction(request, prefix):
    try:
        data = _json_payload(request)
        store, register, session, redirect_response = _require_register_and_session(request, prefix)
        if redirect_response:
            return JsonResponse({"success": False, "error": "Open a register session before processing a sale."}, status=400)
        items = data.get("items", [])
        sale_total = _estimate_sale_total(store, items)
        payment_rows = _payment_rows_from_payload(data, sale_total)
        pos_transaction = create_sale_transaction(
            cashier=request.user,
            store=store,
            session=session,
            terminal=register,
            items_data=items,
            payment_method=data.get("payment_method", "cash"),
            customer_name=data.get("customer_name", ""),
            customer_email=data.get("customer_email", ""),
            customer_phone=data.get("customer_phone", ""),
            notes=data.get("notes", ""),
            payments_data=payment_rows,
        )
        return JsonResponse(
            {
                "success": True,
                "transaction_id": str(pos_transaction.id),
                "transaction_number": pos_transaction.transaction_number,
                "detail_url": reverse("dashboard:pos:sale_detail", kwargs={"prefix": prefix, "transaction_id": pos_transaction.id}),
                "receipt_url": reverse("dashboard:pos:receipt", kwargs={"prefix": prefix, "transaction_id": pos_transaction.id}),
                "invoice_url": reverse("dashboard:pos:invoice", kwargs={"prefix": prefix, "transaction_id": pos_transaction.id}),
            }
        )
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)
    except StoreInventory.DoesNotExist:
        return JsonResponse({"success": False, "error": "One of the selected inventory items no longer exists."}, status=404)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@dashboard_prefix_required
@require_GET
@require_pos_schema_ready(json_mode=True)
@require_feature("max_pos_locations")
def search_products(request, prefix):
    query = request.GET.get("q", "")
    if not query:
        return JsonResponse({"products": []})
    store, redirect_response = _require_place(request, prefix)
    if redirect_response:
        return JsonResponse({"products": []})
    return JsonResponse({"products": search_store_products(store=store, query=query)})


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
def pos_products(request, prefix):
    store, redirect_response = _require_place(request, prefix)
    if redirect_response:
        return redirect_response
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "active").strip()
    edit_product = None
    edit_id = request.GET.get("edit", "").strip()
    if edit_id:
        edit_product = get_object_or_404(active_product_queryset(), pk=edit_id)

    products = active_product_queryset().order_by("name")
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q))
    if status == "active":
        products = products.filter(is_active=True)
    elif status == "inactive":
        products = products.filter(is_active=False)

    inventory_map = {
        inventory.product_id: inventory
        for inventory in StoreInventory.objects.filter(
            store=store,
            product_id__in=products.values_list("id", flat=True),
            is_deleted=False,
        ).select_related("product")
    }
    product_rows = [{"product": product, "inventory": inventory_map.get(product.id)} for product in products]
    form_initial = {"stock_quantity": inventory_map.get(edit_product.id).quantity if edit_product and inventory_map.get(edit_product.id) else 0}
    product_form = POSProductForm(instance=edit_product, initial=form_initial)

    context = _ctx(
        prefix,
        "POS Products",
        "pos_products",
        store=store,
        product_rows=product_rows,
        product_form=product_form,
        edit_product=edit_product,
        q=q,
        selected_status=status,
        create_url=reverse("dashboard:pos:product_create", kwargs={"prefix": prefix}),
        edit_url=reverse("dashboard:pos:product_edit", kwargs={"prefix": prefix, "product_id": edit_product.id}) if edit_product else "",
    )
    return render(request, "dashboard/pos/products.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_http_methods(["POST"])
def create_pos_product(request, prefix):
    store, redirect_response = _require_place(request, prefix)
    if redirect_response:
        return redirect_response
    try:
        form = POSProductForm(request.POST, request.FILES)
        if not form.is_valid():
            raise ValidationError(_form_error_message(form))
        payload = form.cleaned_data
        payload["sku"] = f"POS-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        payload["is_taxable"] = False
        create_quick_pos_product(user=request.user, store=store, payload=payload, image_file=form.cleaned_data.get("image"))
        messages.success(request, "POS product created successfully.")
    except ValidationError as exc:
        messages.error(request, exc.message)
    except Exception as exc:
        messages.error(request, f"Could not create product: {exc}")
    return redirect(reverse("dashboard:pos:products", kwargs={"prefix": prefix, "store": store.id}))


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_http_methods(["POST"])
def edit_pos_product(request, prefix, product_id):
    store, redirect_response = _require_place(request, prefix)
    if redirect_response:
        return redirect_response
    product = get_object_or_404(active_product_queryset(), pk=product_id)
    try:
        form = POSProductForm(request.POST, request.FILES, instance=product)
        if not form.is_valid():
            raise ValidationError(_form_error_message(form))
        update_quick_pos_product(product=product, store=store, payload=form.cleaned_data, user=request.user, image_file=form.cleaned_data.get("image"))
        messages.success(request, "POS product updated successfully.")
    except ValidationError as exc:
        messages.error(request, exc.message)
    except Exception as exc:
        messages.error(request, f"Could not update product: {exc}")
    return redirect(f"{reverse('dashboard:pos:products', kwargs={'prefix': prefix, 'store': store.id})}?edit={product_id}")


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_http_methods(["POST"])
def sync_catalog_bridge_view(request, prefix):
    summary = sync_catalog_bridge(
        user=request.user,
        published_only=request.POST.get("published_only") == "1",
        include_all_active=request.POST.get("include_all_active") == "1",
    )
    messages.success(request, f"POS catalog bridge synced: {summary['created_items']} created, {summary['updated_items']} refreshed.")
    return redirect(reverse("dashboard:pos:products", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_http_methods(["POST"])
def toggle_product(request, prefix, product_id):
    product = get_object_or_404(active_product_queryset(), pk=product_id)
    toggle_product_status(product=product, user=request.user)
    state = "activated" if product.is_active else "deactivated"
    messages.success(request, f"{product.name} {state}.")
    return redirect(reverse("dashboard:pos:products", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
def inventory(request, prefix):
    store, redirect_response = _require_place(request, prefix)
    if redirect_response:
        return redirect_response
    q = request.GET.get("q", "").strip()
    inventory_qs = active_inventory_queryset().select_related(
        "product", "catalog_item", "catalog_item__product", "catalog_item__variant", "store",
    ).filter(store=store).order_by("product__name", "catalog_item__product__name")
    if q:
        inventory_qs = inventory_qs.filter(
            Q(product__name__icontains=q)
            | Q(product__sku__icontains=q)
            | Q(product__barcode__icontains=q)
            | Q(catalog_item__product__name__icontains=q)
            | Q(catalog_item__product__sku__icontains=q)
            | Q(catalog_item__variant__sku__icontains=q)
            | Q(catalog_item__barcode_override__icontains=q)
        )
    summary = {
        "total_items": inventory_qs.count(),
        "low_stock_count": inventory_qs.filter(quantity__gt=0, quantity__lte=F("low_stock_threshold")).count(),
        "out_of_stock_count": inventory_qs.filter(quantity__lte=0).count(),
    }
    adjustments = InventoryAdjustment.objects.filter(
        is_deleted=False,
        store_inventory__in=inventory_qs,
    ).select_related(
        "store_inventory", "store_inventory__product", "store_inventory__catalog_item", "store_inventory__catalog_item__product",
    )[:10]
    context = _ctx(
        prefix,
        "POS Inventory",
        "pos_inventory",
        selected_store=store,
        inventory_items=inventory_qs,
        recent_adjustments=adjustments,
        q=q,
        adjust_url=reverse("dashboard:pos:adjust_inventory", kwargs={"prefix": prefix}),
        **summary,
    )
    return render(request, "dashboard/pos/inventory_report.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def adjust_inventory(request, prefix):
    try:
        payload = request.POST.dict() if request.POST else _json_payload(request)
        inventory = get_object_or_404(active_inventory_queryset(), pk=payload.get("inventory_id"))
        adjusted_inventory, _ = adjust_inventory_service(
            inventory=inventory,
            adjustment_type=payload.get("adjustment_type", "reconciliation"),
            quantity_change=int(payload.get("quantity_change", 0)),
            reason=payload.get("reason", ""),
            reference_number=payload.get("reference_number", ""),
            user=request.user,
        )
        if request.content_type == "application/json":
            return JsonResponse({"success": True, "new_quantity": adjusted_inventory.quantity})
        messages.success(request, f"Inventory updated for {adjusted_inventory.display_name}.")
    except ValidationError as exc:
        if request.content_type == "application/json":
            return JsonResponse({"success": False, "error": exc.message}, status=400)
        messages.error(request, exc.message)
    except Exception as exc:
        if request.content_type == "application/json":
            return JsonResponse({"success": False, "error": str(exc)}, status=500)
        messages.error(request, f"Could not update inventory: {exc}")
    return redirect(reverse("dashboard:pos:inventory", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
def sales(request, prefix):
    store, redirect_response = _require_place(request, prefix)
    if redirect_response:
        return redirect_response
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    status = request.GET.get("status", "").strip()
    cashier_id = request.GET.get("cashier", "").strip()
    payment_method = request.GET.get("payment_method", "").strip()

    transactions = (
        POSTransaction.objects.filter(is_deleted=False, store=store)
        .select_related("store", "cashier", "terminal", "session")
        .prefetch_related("payments")
        .order_by("-created_at")
    )
    if status:
        transactions = transactions.filter(status=status)
    if cashier_id:
        transactions = transactions.filter(cashier_id=cashier_id)
    if payment_method:
        transactions = transactions.filter(payments__payment_method=payment_method)
    if date_from:
        transactions = transactions.filter(created_at__date__gte=date_from)
    if date_to:
        transactions = transactions.filter(created_at__date__lte=date_to)
    transactions = transactions.distinct()

    totals = transactions.aggregate(total_sales=Sum("total_amount"))
    cashiers = (
        TenantUser.objects.filter(pos_transactions__store=store, pos_transactions__is_deleted=False)
        .distinct()
        .order_by("first_name", "last_name", "email")
    )
    context = _ctx(
        prefix,
        "POS Sales",
        "pos_sales",
        selected_store=store,
        transactions=transactions[:100],
        total_sales=totals["total_sales"] or 0,
        transaction_count=transactions.count(),
        cashiers=cashiers,
        payment_method_options=PAYMENT_METHOD_OPTIONS,
        selected_status=status,
        selected_cashier=cashier_id,
        selected_payment_method=payment_method,
        date_from=date_from,
        date_to=date_to,
    )
    return render(request, "dashboard/pos/sales_report.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_http_methods(["GET", "POST"])
def sale_detail(request, prefix, transaction_id):
    transaction = get_object_or_404(
        POSTransaction.objects.select_related("store", "cashier", "session", "terminal").prefetch_related("items", "payments"),
        pk=transaction_id,
        is_deleted=False,
    )
    if request.method == "POST" and request.POST.get("action") == "refund":
        try:
            refund = refund_transaction(transaction=transaction, cashier=request.user, reason=request.POST.get("reason", ""))
            messages.success(request, f"Refund recorded as {refund.transaction_number}.")
            return redirect(reverse("dashboard:pos:sale_detail", kwargs={"prefix": prefix, "transaction_id": refund.id}))
        except ValidationError as exc:
            messages.error(request, exc.message)
    context = _ctx(prefix, f"Sale {transaction.transaction_number}", "pos_sales", transaction=transaction)
    return render(request, "dashboard/pos/sale_detail.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
def discounts(request, prefix):
    discounts_qs = active_discount_queryset()
    context = _ctx(prefix, "POS Discounts", "pos_discounts", discounts=discounts_qs)
    return render(request, "dashboard/pos/discounts.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
@require_feature("max_pos_locations")
def generate_receipt(request, prefix, transaction_id):
    transaction = get_object_or_404(
        POSTransaction.objects.select_related("store", "cashier", "session", "terminal").prefetch_related("items", "payments"),
        pk=transaction_id,
        is_deleted=False,
    )
    context = build_receipt_context(transaction)
    context.update({"prefix": prefix})
    return _render_receipt_response(request, "dashboard/pos/receipt.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready()
def pos_register(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return redirect_response
    cart = get_or_create_active_cart(cashier=request.user, store=store)
    cart_data = get_cart_context(cart)
    inventory_qs = active_inventory_queryset().filter(store=store).select_related(
        "product", "catalog_item", "catalog_item__product", "catalog_item__variant"
    )
    inventory_summary = {
        "low_stock_count": inventory_qs.filter(quantity__gt=0, quantity__lte=models.F("low_stock_threshold")).count(),
        "out_of_stock_count": inventory_qs.filter(quantity=0).count(),
        "total_products": inventory_qs.count(),
    }
    held_carts = POSCart.objects.filter(cashier=request.user, store=store, status=POSCart.Status.HELD).order_by("-held_at")[:20]
    context = _ctx(
        prefix,
        "POS Register",
        "pos_register",
        store=store,
        register=register,
        active_session=session,
        cart=cart,
        cart_data=cart_data,
        held_carts=held_carts,
        inventory_summary=inventory_summary,
        payment_method_options=PAYMENT_METHOD_OPTIONS,
        search_url=reverse("dashboard:pos:search_products", kwargs={"prefix": prefix}),
        cart_add_url=reverse("dashboard:pos:cart_add", kwargs={"prefix": prefix}),
        cart_update_url=reverse("dashboard:pos:cart_update", kwargs={"prefix": prefix}),
        cart_remove_url=reverse("dashboard:pos:cart_remove", kwargs={"prefix": prefix}),
        cart_hold_url=reverse("dashboard:pos:cart_hold", kwargs={"prefix": prefix}),
        cart_resume_url=reverse("dashboard:pos:cart_resume", kwargs={"prefix": prefix}),
        cart_clear_url=reverse("dashboard:pos:cart_clear", kwargs={"prefix": prefix}),
        cart_checkout_url=reverse("dashboard:pos:cart_checkout", kwargs={"prefix": prefix}),
        offline_sync_url=reverse("dashboard:pos:offline_sync", kwargs={"prefix": prefix}),
        tax_rate=float(store.tax_rate or 0),
    )
    return render(request, "dashboard/pos/register.html", context)


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def cart_api_add(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return JsonResponse({"success": False, "error": "Open a register session before using the cart."}, status=400)
    data = _json_payload(request)
    inventory_id = data.get("inventory_id", "")
    if not inventory_id:
        return JsonResponse({"success": False, "error": "inventory_id is required."}, status=400)
    cart = get_or_create_active_cart(cashier=request.user, store=store)
    try:
        add_item_to_cart(cart=cart, inventory_id=inventory_id, store=store)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)
    return JsonResponse({"success": True, "cart": get_cart_context(cart)})


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def cart_api_update(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return JsonResponse({"success": False, "error": "Open a register session before using the cart."}, status=400)
    data = _json_payload(request)
    item_id = data.get("item_id", "")
    quantity = data.get("quantity")
    if not item_id or quantity is None:
        return JsonResponse({"success": False, "error": "item_id and quantity are required."}, status=400)
    cart = get_or_create_active_cart(cashier=request.user, store=store)
    try:
        item = get_object_or_404(POSCartItem, id=item_id, cart=cart)
        update_cart_item_quantity(cart_item=item, quantity=int(quantity))
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)
    return JsonResponse({"success": True, "cart": get_cart_context(cart)})


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def cart_api_remove(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return JsonResponse({"success": False, "error": "Open a register session before using the cart."}, status=400)
    data = _json_payload(request)
    item_id = data.get("item_id", "")
    if not item_id:
        return JsonResponse({"success": False, "error": "item_id is required."}, status=400)
    cart = get_or_create_active_cart(cashier=request.user, store=store)
    try:
        item = get_object_or_404(POSCartItem, id=item_id, cart=cart)
        remove_cart_item(cart_item=item)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)
    return JsonResponse({"success": True, "cart": get_cart_context(cart)})


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def cart_api_hold(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return JsonResponse({"success": False, "error": "Open a register session before using the cart."}, status=400)
    cart = get_or_create_active_cart(cashier=request.user, store=store)
    try:
        hold_cart(cart=cart, reference=_json_payload(request).get("reference", ""))
        new_cart = get_or_create_active_cart(cashier=request.user, store=store)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)
    return JsonResponse({"success": True, "cart": get_cart_context(new_cart)})


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def cart_api_resume(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return JsonResponse({"success": False, "error": "Open a register session before using the cart."}, status=400)
    data = _json_payload(request)
    cart = get_object_or_404(POSCart, pk=data.get("cart_id"), cashier=request.user, store=store)
    try:
        resume_cart(cart=cart)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)
    return JsonResponse({"success": True, "cart": get_cart_context(cart)})


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def cart_api_clear(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return JsonResponse({"success": False, "error": "Open a register session before using the cart."}, status=400)
    cart = get_or_create_active_cart(cashier=request.user, store=store)
    try:
        void_cart(cart=cart)
        new_cart = get_or_create_active_cart(cashier=request.user, store=store)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)
    return JsonResponse({"success": True, "cart": get_cart_context(new_cart)})


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def cart_api_checkout(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return JsonResponse({"success": False, "error": "Open a register session before using the cart."}, status=400)
    data = _json_payload(request)
    payment_method = data.get("payment_method", "cash")
    cart = get_or_create_active_cart(cashier=request.user, store=store)
    try:
        txn = checkout_cart(
            cart=cart,
            payment_method=payment_method,
            customer_name=data.get("customer_name", ""),
            customer_email=data.get("customer_email", ""),
            customer_phone=data.get("customer_phone", ""),
            notes=data.get("notes", ""),
            cashier=request.user,
            session=session,
            terminal=register,
            payments_data=_payment_rows_from_payload(
                data,
                _estimate_sale_total(
                    store,
                    [
                        {"inventory_id": item.store_inventory_id, "quantity": item.quantity}
                        for item in cart.items.select_related("store_inventory")
                    ],
                ),
            ),
        )
    except ValidationError as exc:
        msg = exc.message if hasattr(exc, "message") else str(exc)
        return JsonResponse({"success": False, "error": msg}, status=400)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
    return JsonResponse({
        "success": True,
        "transaction_number": txn.transaction_number,
        "receipt_url": reverse("dashboard:pos:receipt", kwargs={"prefix": prefix, "transaction_id": txn.id}),
        "detail_url": reverse("dashboard:pos:sale_detail", kwargs={"prefix": prefix, "transaction_id": txn.id}),
        "invoice_url": reverse("dashboard:pos:invoice", kwargs={"prefix": prefix, "transaction_id": txn.id}),
    })


@login_required
@dashboard_prefix_required
@require_pos_schema_ready(json_mode=True)
@require_http_methods(["POST"])
def offline_sync(request, prefix):
    store, register, session, redirect_response = _require_register_and_session(request, prefix)
    if redirect_response:
        return JsonResponse({"success": False, "error": "Open a register session before syncing offline sales."}, status=400)
    data = _json_payload(request)
    payloads = data.get("transactions", [])
    synced = []
    for payload in payloads:
        txn = sync_offline_transaction(cashier=request.user, store=store, terminal=register, session=session, payload=payload)
        synced.append(
            {
                "client_transaction_id": payload.get("client_transaction_id"),
                "transaction_number": txn.transaction_number,
                "receipt_url": reverse("dashboard:pos:receipt", kwargs={"prefix": prefix, "transaction_id": txn.id}),
                "invoice_url": reverse("dashboard:pos:invoice", kwargs={"prefix": prefix, "transaction_id": txn.id}),
                "detail_url": reverse("dashboard:pos:sale_detail", kwargs={"prefix": prefix, "transaction_id": txn.id}),
            }
        )
    return JsonResponse({"success": True, "transactions": synced})
