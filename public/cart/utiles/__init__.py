"""
orders/utils/__init__.py
========================
Public surface of the orders utility layer.

Import from here rather than from sub-modules directly:

    from orders.utils import (
        get_or_create_cart,
        add_item_to_cart,
        place_order,
        get_order_dashboard_summary,
        get_revenue_chart_data,
    )

Sub-modules:
    cart        → cart lifecycle, item management, session resolution
    order       → order creation, transitions, number generation
    fulfillment → fulfillment creation, tracking sync, status updates
    returns     → RMA creation, inspection, disposition workflow
    analytics   → time-series revenue, funnel metrics, product stats
    dashboard   → aggregated KPI blocks ready for dashboard views
"""

from .cart import (
    get_or_create_cart,
    get_cart_by_token,
    add_item_to_cart,
    update_cart_item_quantity,
    remove_cart_item,
    apply_discount_code,
    remove_discount_code,
    apply_gift_card,
    recalculate_cart_totals,
    merge_guest_cart_into_user_cart,
    capture_checkout_email,
    mark_cart_abandoned,
    get_recoverable_carts,
    get_client_ip,
)

from .order import (
    generate_order_number,
    place_order_from_cart,
    confirm_order,
    cancel_order,
    get_order_for_customer,
    get_orders_for_customer,
    get_order_timeline,
    reorder,
    validate_checkout_data,
    calculate_order_totals,
)

from .fulfillment import (
    create_fulfillment,
    mark_fulfillment_shipped,
    mark_fulfillment_delivered,
    cancel_fulfillment,
    sync_tracking_status,
    get_unfulfilled_orders,
    get_fulfillment_summary,
    build_fulfillment_number,
)

from .returns import (
    create_return_request,
    approve_return,
    reject_return,
    receive_return_items,
    inspect_return_items,
    complete_return_restock,
    create_refund_from_return,
    create_standalone_refund,
    process_refund,
    get_returnable_items,
)

from .analytics import (
    get_revenue_over_time,
    get_orders_over_time,
    get_average_order_value,
    get_conversion_funnel,
    get_top_products_by_revenue,
    get_top_customers_by_spend,
    get_order_status_distribution,
    get_fulfillment_performance,
    get_return_rate_stats,
    get_sales_by_channel,
    get_geographic_breakdown,
    get_cohort_retention,
)

from .dashboard import (
    get_dashboard_kpis,
    get_recent_orders,
    get_orders_needing_attention,
    get_low_stock_order_risks,
    get_pending_returns_summary,
    get_revenue_comparison,
    get_todays_stats,
    get_order_fulfillment_queue,
)

__all__ = [
    # cart
    "get_or_create_cart", "get_cart_by_token", "add_item_to_cart",
    "update_cart_item_quantity", "remove_cart_item", "apply_discount_code",
    "remove_discount_code", "apply_gift_card", "recalculate_cart_totals",
    "merge_guest_cart_into_user_cart", "capture_checkout_email",
    "mark_cart_abandoned", "get_recoverable_carts", "get_client_ip",
    # order
    "generate_order_number", "place_order_from_cart", "confirm_order",
    "cancel_order", "get_order_for_customer", "get_orders_for_customer",
    "get_order_timeline", "reorder", "validate_checkout_data",
    "calculate_order_totals",
    # fulfillment
    "create_fulfillment", "mark_fulfillment_shipped", "mark_fulfillment_delivered",
    "cancel_fulfillment", "sync_tracking_status", "get_unfulfilled_orders",
    "get_fulfillment_summary", "build_fulfillment_number",
    # returns
    "create_return_request", "approve_return", "reject_return",
    "receive_return_items", "inspect_return_items", "complete_return_restock",
    "create_refund_from_return", "create_standalone_refund", "process_refund",
    "get_returnable_items",
    # analytics
    "get_revenue_over_time", "get_orders_over_time", "get_average_order_value",
    "get_conversion_funnel", "get_top_products_by_revenue",
    "get_top_customers_by_spend", "get_order_status_distribution",
    "get_fulfillment_performance", "get_return_rate_stats", "get_sales_by_channel",
    "get_geographic_breakdown", "get_cohort_retention",
    # dashboard
    "get_dashboard_kpis", "get_recent_orders", "get_orders_needing_attention",
    "get_low_stock_order_risks", "get_pending_returns_summary",
    "get_revenue_comparison", "get_todays_stats", "get_order_fulfillment_queue",
]
