"""
dashboard/pricing/urls.py
==========================
URL config for the Pricing & Promotions dashboard section.
Namespace: pricing  (full: dashboard:pricing:...)

URL hierarchy for child models (Q1=b — separate pages):
  /pricing/price-lists/<uuid>/assignments/
  /pricing/price-lists/<uuid>/entries/
  /pricing/discount-codes/<uuid>/rules/
  /pricing/discount-codes/<uuid>/usages/
  /pricing/automatic-discounts/<uuid>/conditions/
  /pricing/automatic-discounts/<uuid>/benefits/
  /pricing/bxgy/<uuid>/items/
  /pricing/flash-sales/<uuid>/items/
"""
from django.urls import path
from dashboard.pricing import views

app_name = "pricing"

urlpatterns = [

    # ── CURRENCY ─────────────────────────────────────────────
    path("currencies/", views.currency_list, name="currency_list"),
    path("currencies/add/", views.currency_create, name="currency_create"),
    path("currencies/<uuid:pk>/edit/", views.currency_edit, name="currency_edit"),
    path("currencies/<uuid:pk>/delete/",
         views.currency_delete, name="currency_delete"),

    # ── EXCHANGE RATE ─────────────────────────────────────────
    path("exchange-rates/", views.exchange_rate_list, name="exchange_rate_list"),
    path("exchange-rates/add/", views.exchange_rate_create,
         name="exchange_rate_create"),
    path("exchange-rates/<uuid:pk>/edit/",
         views.exchange_rate_edit, name="exchange_rate_edit"),
    path("exchange-rates/<uuid:pk>/delete/",
         views.exchange_rate_delete, name="exchange_rate_delete"),

    # ── PRICE LIST ────────────────────────────────────────────
    path("price-lists/", views.price_list_list, name="price_list_list"),
    path("price-lists/add/", views.price_list_create, name="price_list_create"),
    path("price-lists/<int:pk>/", views.price_list_detail,
         name="price_list_detail"),
    path("price-lists/<int:pk>/edit/",
         views.price_list_edit, name="price_list_edit"),
    path("price-lists/<int:pk>/delete/",
         views.price_list_delete, name="price_list_delete"),

    # ── PRICE LIST ASSIGNMENTS (child) ────────────────────────
    path("price-lists/<int:price_list_pk>/assignments/",
         views.price_list_assignment_list, name="price_list_assignment_list"),
    path("price-lists/<int:price_list_pk>/assignments/add/",
         views.price_list_assignment_create, name="price_list_assignment_create"),
    path("price-lists/<uuid:price_list_pk>/assignments/<uuid:pk>/edit/",
         views.price_list_assignment_edit, name="price_list_assignment_edit"),
    path("price-lists/<uuid:price_list_pk>/assignments/<uuid:pk>/delete/",
         views.price_list_assignment_delete, name="price_list_assignment_delete"),

    # ── PRICE LIST ENTRIES (child) ────────────────────────────
    path("price-lists/<int:price_list_pk>/entries/",
         views.price_list_entry_list, name="price_list_entry_list"),
    path("price-lists/<uuid:price_list_pk>/entries/add/",
         views.price_list_entry_create, name="price_list_entry_create"),
    path("price-lists/<uuid:price_list_pk>/entries/<uuid:pk>/edit/",
         views.price_list_entry_edit, name="price_list_entry_edit"),
    path("price-lists/<uuid:price_list_pk>/entries/<uuid:pk>/delete/",
         views.price_list_entry_delete, name="price_list_entry_delete"),

    # ── DISCOUNT CODE ─────────────────────────────────────────
    path("discount-codes/", views.discount_code_list, name="discount_code_list"),
    path("discount-codes/add/", views.discount_code_create,
         name="discount_code_create"),
    path("discount-codes/<uuid:pk>/", views.discount_code_detail,
         name="discount_code_detail"),
    path("discount-codes/<uuid:pk>/edit/",
         views.discount_code_edit, name="discount_code_edit"),
    path("discount-codes/<uuid:pk>/delete/",
         views.discount_code_delete, name="discount_code_delete"),

    # ── DISCOUNT RULE (child) ─────────────────────────────────
    path("discount-codes/<uuid:code_pk>/rules/",
         views.discount_rule_list, name="discount_rule_list"),
    path("discount-codes/<uuid:code_pk>/rules/add/",
         views.discount_rule_create, name="discount_rule_create"),
    path("discount-codes/<uuid:code_pk>/rules/<uuid:pk>/edit/",
         views.discount_rule_edit, name="discount_rule_edit"),
    path("discount-codes/<uuid:code_pk>/rules/<uuid:pk>/delete/",
         views.discount_rule_delete, name="discount_rule_delete"),

    # ── DISCOUNT USAGE (read-only, child) ─────────────────────
    path("discount-codes/<uuid:code_pk>/usages/",
         views.discount_usage_list, name="discount_usage_list"),

    # ── AUTOMATIC DISCOUNT ────────────────────────────────────
    path("automatic-discounts/", views.automatic_discount_list,
         name="automatic_discount_list"),
    path("automatic-discounts/add/", views.automatic_discount_create,
         name="automatic_discount_create"),
    path("automatic-discounts/<uuid:pk>/",
         views.automatic_discount_detail, name="automatic_discount_detail"),
    path("automatic-discounts/<uuid:pk>/edit/",
         views.automatic_discount_edit, name="automatic_discount_edit"),
    path("automatic-discounts/<uuid:pk>/delete/",
         views.automatic_discount_delete, name="automatic_discount_delete"),

    # ── AUTO DISCOUNT CONDITIONS (child) ──────────────────────
    path("automatic-discounts/<uuid:discount_pk>/conditions/",
         views.auto_condition_list, name="auto_condition_list"),
    path("automatic-discounts/<uuid:discount_pk>/conditions/add/",
         views.auto_condition_create, name="auto_condition_create"),
    path("automatic-discounts/<uuid:discount_pk>/conditions/<uuid:pk>/edit/",
         views.auto_condition_edit, name="auto_condition_edit"),
    path("automatic-discounts/<uuid:discount_pk>/conditions/<uuid:pk>/delete/",
         views.auto_condition_delete, name="auto_condition_delete"),

    # ── AUTO DISCOUNT BENEFITS (child) ───────────────────────
    path("automatic-discounts/<uuid:discount_pk>/benefits/",
         views.auto_benefit_list, name="auto_benefit_list"),
    path("automatic-discounts/<uuid:discount_pk>/benefits/add/",
         views.auto_benefit_create, name="auto_benefit_create"),
    path("automatic-discounts/<uuid:discount_pk>/benefits/<uuid:pk>/edit/",
         views.auto_benefit_edit, name="auto_benefit_edit"),
    path("automatic-discounts/<uuid:discount_pk>/benefits/<uuid:pk>/delete/",
         views.auto_benefit_delete, name="auto_benefit_delete"),

    # ── BUY X GET Y PROMOTION ─────────────────────────────────
    path("bxgy/", views.bxgy_list, name="bxgy_list"),
    path("bxgy/add/", views.bxgy_create, name="bxgy_create"),
    path("bxgy/<uuid:pk>/", views.bxgy_detail, name="bxgy_detail"),
    path("bxgy/<uuid:pk>/edit/", views.bxgy_edit, name="bxgy_edit"),
    path("bxgy/<uuid:pk>/delete/", views.bxgy_delete, name="bxgy_delete"),

    # ── BUY X GET Y ITEMS (child) ─────────────────────────────
    path("bxgy/<uuid:promotion_pk>/items/",
         views.bxgy_item_list, name="bxgy_item_list"),
    path("bxgy/<uuid:promotion_pk>/items/add/",
         views.bxgy_item_create, name="bxgy_item_create"),
    path("bxgy/<uuid:promotion_pk>/items/<uuid:pk>/edit/",
         views.bxgy_item_edit, name="bxgy_item_edit"),
    path("bxgy/<uuid:promotion_pk>/items/<uuid:pk>/delete/",
         views.bxgy_item_delete, name="bxgy_item_delete"),

    # ── VOLUME PRICING TIER ───────────────────────────────────
    path("volume-tiers/", views.volume_tier_list, name="volume_tier_list"),
    path("volume-tiers/add/", views.volume_tier_create, name="volume_tier_create"),
    path("volume-tiers/<uuid:pk>/edit/",
         views.volume_tier_edit, name="volume_tier_edit"),
    path("volume-tiers/<uuid:pk>/delete/",
         views.volume_tier_delete, name="volume_tier_delete"),

    # ── FLASH SALE ────────────────────────────────────────────
    path("flash-sales/", views.flash_sale_list, name="flash_sale_list"),
    path("flash-sales/add/", views.flash_sale_create, name="flash_sale_create"),
    path("flash-sales/<uuid:pk>/", views.flash_sale_detail,
         name="flash_sale_detail"),
    path("flash-sales/<uuid:pk>/edit/",
         views.flash_sale_edit, name="flash_sale_edit"),
    path("flash-sales/<uuid:pk>/delete/",
         views.flash_sale_delete, name="flash_sale_delete"),

    # ── FLASH SALE ITEMS (child) ──────────────────────────────
    path("flash-sales/<uuid:sale_pk>/items/",
         views.flash_sale_item_list, name="flash_sale_item_list"),
    path("flash-sales/<uuid:sale_pk>/items/add/",
         views.flash_sale_item_create, name="flash_sale_item_create"),
    path("flash-sales/<uuid:sale_pk>/items/<uuid:pk>/edit/",
         views.flash_sale_item_edit, name="flash_sale_item_edit"),
    path("flash-sales/<uuid:sale_pk>/items/<uuid:pk>/delete/",
         views.flash_sale_item_delete, name="flash_sale_item_delete"),

    # ── TAX CATEGORY ──────────────────────────────────────────
    path("tax-categories/", views.tax_category_list, name="tax_category_list"),
    path("tax-categories/add/", views.tax_category_create,
         name="tax_category_create"),
    path("tax-categories/<uuid:pk>/edit/",
         views.tax_category_edit, name="tax_category_edit"),
    path("tax-categories/<uuid:pk>/delete/",
         views.tax_category_delete, name="tax_category_delete"),

    # ── TAX ZONE ──────────────────────────────────────────────
    path("tax-zones/", views.tax_zone_list, name="tax_zone_list"),
    path("tax-zones/add/", views.tax_zone_create, name="tax_zone_create"),
    path("tax-zones/<uuid:pk>/edit/", views.tax_zone_edit, name="tax_zone_edit"),
    path("tax-zones/<uuid:pk>/delete/",
         views.tax_zone_delete, name="tax_zone_delete"),

    # ── TAX RATE ──────────────────────────────────────────────
    path("tax-rates/", views.tax_rate_list, name="tax_rate_list"),
    path("tax-rates/add/", views.tax_rate_create, name="tax_rate_create"),
    path("tax-rates/<uuid:pk>/edit/", views.tax_rate_edit, name="tax_rate_edit"),
    path("tax-rates/<uuid:pk>/delete/",
         views.tax_rate_delete, name="tax_rate_delete"),
]
