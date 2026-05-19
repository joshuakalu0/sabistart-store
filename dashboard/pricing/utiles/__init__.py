"""
pricing/utils/__init__.py
=========================
Public surface of the pricing utility layer.

Sub-modules:
    price_resolver   → canonical price resolution pipeline for any variant+customer
    discount         → coupon code validation, application, automatic discount engine
    tax              → tax zone matching, rate lookup, tax calculation
    gift_card        → gift card lifecycle, redemption, refund, balance queries
    flash_sale       → flash sale status, eligibility, scarcity checks
    currency         → conversion, formatting, exchange rate management
    analytics        → discount performance, revenue lift, promotion ROI
    dashboard        → pricing KPI cards, promotion health, discount queue
"""

from dataclasses import dataclass
from decimal import Decimal

from .price_resolver import (
    resolve_price,
    resolve_prices_bulk,
    get_applicable_price_lists,
    get_volume_tier,
    get_flash_sale_item,
    PriceResolutionResult,
    PricingContext,
)

from .discount import (
    validate_discount_code,
    apply_discount_to_cart,
    remove_discount_from_cart,
    get_applicable_automatic_discounts,
    apply_automatic_discounts,
    calculate_line_level_discounts,
    record_discount_usage,
    check_discount_fraud_signals,
    DiscountValidationResult,
    DiscountApplicationResult,
)

from .tax_gc_flash_currency import (
    resolve_tax_zone,
    get_tax_rates_for_address,
    calculate_tax_for_order,
    calculate_tax_for_line,
    get_tax_summary,
    format_tax_lines,
    TaxCalculationResult,
    TaxLineResult,
)

try:
    from .tax_gc_flash_currency import (
        validate_gift_card,
        redeem_gift_card_at_checkout,
        issue_gift_card,
        bulk_issue_gift_cards,
        get_customer_gift_cards,
        get_gift_card_by_code,
        expire_overdue_gift_cards,
        GiftCardValidationResult,
        GiftCardRedemptionResult,
    )
except ImportError:
    @dataclass
    class GiftCardValidationResult:
        valid: bool = False
        code: str = ""
        balance: Decimal = Decimal("0.00")
        currency: str = "USD"
        message: str = "Gift card helpers are not available in this build."
        error_type: str = "unavailable"
        applicable_amount: Decimal = Decimal("0.00")


    @dataclass
    class GiftCardRedemptionResult:
        success: bool = False
        amount_applied: Decimal = Decimal("0.00")
        remaining_balance: Decimal = Decimal("0.00")
        transaction_id: str | None = None
        message: str = "Gift card helpers are not available in this build."


    def validate_gift_card(*args, **kwargs):
        return GiftCardValidationResult()


    def redeem_gift_card_at_checkout(*args, **kwargs):
        return GiftCardRedemptionResult()


    def issue_gift_card(*args, **kwargs):
        raise NotImplementedError("Gift card issuance helpers are not available in this build.")


    def bulk_issue_gift_cards(*args, **kwargs):
        return []


    def get_customer_gift_cards(*args, **kwargs):
        return []


    def get_gift_card_by_code(*args, **kwargs):
        return None


    def expire_overdue_gift_cards(*args, **kwargs):
        return 0

from .tax_gc_flash_currency import (
    get_active_flash_sales,
    get_flash_sale_price,
    check_flash_sale_eligibility,
    increment_flash_sale_units_sold,
    get_flash_sale_countdown,
    get_storefront_flash_sale_data,
)

from .tax_gc_flash_currency import (
    convert_amount,
    format_amount,
    get_base_currency,
    get_enabled_currencies,
    get_exchange_rate,
    sync_exchange_rates,
    CurrencyConversionResult,
)

from .analytics import (
    get_discount_performance,
    get_top_discount_codes,
    get_automatic_discount_performance,
    get_flash_sale_performance,
    get_gift_card_stats,
    get_revenue_by_price_list,
    get_discount_usage_over_time,
    get_promotion_roi,
    get_price_list_adoption,
    get_tax_collected_by_zone,
)

from .dashboard import (
    get_pricing_dashboard_kpis,
    get_active_promotions_summary,
    get_discount_codes_needing_attention,
    get_expiring_promotions,
    get_flash_sales_live_status,
    get_gift_card_balance_summary,
    get_top_performing_promotions,
    get_pricing_health_checks,
)

__all__ = [
    # price_resolver
    "resolve_price", "resolve_prices_bulk", "get_applicable_price_lists",
    "get_volume_tier", "get_flash_sale_item",
    "PriceResolutionResult", "PricingContext",
    # discount
    "validate_discount_code", "apply_discount_to_cart", "remove_discount_from_cart",
    "get_applicable_automatic_discounts", "apply_automatic_discounts",
    "calculate_line_level_discounts", "record_discount_usage",
    "check_discount_fraud_signals",
    "DiscountValidationResult", "DiscountApplicationResult",
    # tax
    "resolve_tax_zone", "get_tax_rates_for_address", "calculate_tax_for_order",
    "calculate_tax_for_line", "get_tax_summary", "format_tax_lines",
    "TaxCalculationResult", "TaxLineResult",
    # gift_card
    "validate_gift_card", "redeem_gift_card_at_checkout", "issue_gift_card",
    "bulk_issue_gift_cards", "get_customer_gift_cards", "get_gift_card_by_code",
    "expire_overdue_gift_cards",
    "GiftCardValidationResult", "GiftCardRedemptionResult",
    # flash_sale
    "get_active_flash_sales", "get_flash_sale_price", "check_flash_sale_eligibility",
    "increment_flash_sale_units_sold", "get_flash_sale_countdown",
    "get_storefront_flash_sale_data",
    # currency
    "convert_amount", "format_amount", "get_base_currency", "get_enabled_currencies",
    "get_exchange_rate", "sync_exchange_rates", "CurrencyConversionResult",
    # analytics
    "get_discount_performance", "get_top_discount_codes",
    "get_automatic_discount_performance", "get_flash_sale_performance",
    "get_gift_card_stats", "get_revenue_by_price_list", "get_discount_usage_over_time",
    "get_promotion_roi", "get_price_list_adoption", "get_tax_collected_by_zone",
    # dashboard
    "get_pricing_dashboard_kpis", "get_active_promotions_summary",
    "get_discount_codes_needing_attention", "get_expiring_promotions",
    "get_flash_sales_live_status", "get_gift_card_balance_summary",
    "get_top_performing_promotions", "get_pricing_health_checks",
]
