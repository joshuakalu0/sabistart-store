"""
pricing/models.py  (combined — import everything from sub-parts)
================================================================
App 9 — Pricing Domain
This file merges all three model parts into the single models.py
that Django expects for the `pricing` app.

Usage:
    from pricing.models import (
        Currency, ExchangeRate,
        PriceList, PriceListCustomerGroup, PriceListEntry,
        DiscountCode, DiscountRule, DiscountUsage,
        AutomaticDiscount, AutomaticDiscountCondition, AutomaticDiscountBenefit,
        BuyXGetYPromotion, BuyXGetYItem,
        VolumePricingTier, FlashSale, FlashSaleItem,
        GiftCardTemplate, GiftCard, GiftCardTransaction,
        TaxCategory, TaxZone, TaxRate,
    )
"""

# ── Section 1 & 2: Abstracts, Currency, Exchange Rates, Price Lists ──
from .part1 import (
    Currency,
    ExchangeRate,
    PriceList,
    PriceListCustomerGroup,
    PriceListEntry,
)

# ── Section 3, 4 & 5: Discount Codes, Automatic Discounts, Promotions ──
from .part2 import (
    DiscountCode,
    DiscountRule,
    DiscountUsage,
    AutomaticDiscount,
    AutomaticDiscountCondition,
    AutomaticDiscountBenefit,
    BuyXGetYPromotion,
    BuyXGetYItem,
    VolumePricingTier,
    FlashSale,
    FlashSaleItem,
)

# ── Section 6 & 7: Gift Cards, Tax Engine ──
from .part3 import (
    # GiftCardTemplate,
    # GiftCard,
    # GiftCardTransaction,
    TaxCategory,
    TaxZone,
    TaxRate,
)

from .part4 import (
    PromotionPartner,
    PromotionLink,
    DiscountExperiment,
    DiscountExperimentVariant,
    DiscountExperimentAssignment,
    DiscountExperimentSnapshot,
    PromotionCompatibilityRule,
    PromotionConflictRecord,
    DiscountImportBatch,
    DiscountImportRow,
    PricingAutomationRule,
    IssuedDiscountCode,
    PricingAutomationDeliveryLog,
    BundleOffer,
    BundleOfferItem,
    BundleOrderLedger,
    PromotionCommissionLedger,
    build_promo_qr_svg,
)

__all__ = [
    # Abstracts

    # Section 1 — Currency
    "Currency",
    "ExchangeRate",
    # Section 2 — Price Lists
    "PriceList",
    "PriceListCustomerGroup",
    "PriceListEntry",
    # Section 3 — Discount Codes
    "DiscountCode",
    "DiscountRule",
    "DiscountUsage",
    # Section 4 — Automatic Discounts
    "AutomaticDiscount",
    "AutomaticDiscountCondition",
    "AutomaticDiscountBenefit",
    # Section 5 — Advanced Promotions
    "BuyXGetYPromotion",
    "BuyXGetYItem",
    "VolumePricingTier",
    "FlashSale",
    "FlashSaleItem",
    # Section 6 — Gift Cards
    # "GiftCardTemplate",
    # "GiftCard",
    # "GiftCardTransaction",
    # Section 7 — Tax Engine
    "TaxCategory",
    "TaxZone",
    "TaxRate",
    # Section 8 — Advanced pricing workflows
    "PromotionPartner",
    "PromotionLink",
    "DiscountExperiment",
    "DiscountExperimentVariant",
    "DiscountExperimentAssignment",
    "DiscountExperimentSnapshot",
    "PromotionCompatibilityRule",
    "PromotionConflictRecord",
    "DiscountImportBatch",
    "DiscountImportRow",
    "PricingAutomationRule",
    "IssuedDiscountCode",
    "PricingAutomationDeliveryLog",
    "BundleOffer",
    "BundleOfferItem",
    "BundleOrderLedger",
    "PromotionCommissionLedger",
    "build_promo_qr_svg",
]
