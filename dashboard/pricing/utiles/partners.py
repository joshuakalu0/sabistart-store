from __future__ import annotations

import secrets
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Sum
from django.utils.text import slugify

from dashboard.pricing.models import (
    DiscountCode,
    PromotionCommissionLedger,
    PromotionLink,
    PromotionPartner,
)
from dashboard.pricing.utiles.advanced import build_promotion_link


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def ensure_customer_referral_partner(customer):
    if customer is None or getattr(customer, "user", None) is None:
        return None
    if not customer.referral_code:
        customer.referral_code = f"REF-{secrets.token_hex(3).upper()}"
        customer.save(update_fields=["referral_code", "updated_at"])
    referral_slug = slugify(customer.referral_code) or slugify(str(customer.id))
    partner, _ = PromotionPartner.objects.get_or_create(
        slug=f"customer-{customer.id}",
        defaults={
            "name": customer.display_name or customer.user.email or f"Customer {customer.id}",
            "partner_type": PromotionPartner.PartnerType.REFERRAL,
            "email": customer.user.email or "",
            "code_prefix": customer.referral_code,
            "referral_slug": referral_slug,
            "default_utm_source": "referral",
            "default_utm_medium": "customer-share",
            "default_utm_campaign": "customer-referral",
        },
    )
    dirty = []
    if not partner.referral_slug:
        partner.referral_slug = referral_slug
        dirty.append("referral_slug")
    if not partner.code_prefix:
        partner.code_prefix = customer.referral_code
        dirty.append("code_prefix")
    if not partner.email and customer.user.email:
        partner.email = customer.user.email
        dirty.append("email")
    if dirty:
        dirty.append("updated_at")
        partner.save(update_fields=dirty)
    return partner


def get_partner_primary_discount(partner):
    if partner is None:
        return None
    return (
        DiscountCode.objects.filter(attributed_partner=partner, is_active=True)
        .order_by("-usage_count", "code")
        .first()
    )


def build_partner_share_bundle(request, partner, *, discount_code=None):
    if partner is None:
        return None
    discount_code = discount_code or get_partner_primary_discount(partner)
    link = build_promotion_link(
        discount_code=discount_code,
        partner=partner,
        landing_path="/promotions/referrals/join/",
        utm_source=partner.default_utm_source or "referral",
        utm_medium=partner.default_utm_medium or "customer-share",
        utm_campaign=partner.default_utm_campaign or "customer-referral",
    )
    params = {
        "ref": partner.referral_slug,
        "utm_source": link.utm_source or "referral",
        "utm_medium": link.utm_medium or "customer-share",
        "utm_campaign": link.utm_campaign or "customer-referral",
    }
    if discount_code is not None:
        params["code"] = discount_code.code
    share_url = request.build_absolute_uri(f"{link.landing_path}?{urlencode(params)}")
    return {
        "link": link,
        "share_url": share_url,
        "qr_svg": link.qr_svg,
        "discount_code": discount_code,
    }


def build_partner_dashboard_bundle(request, customer):
    partner = ensure_customer_referral_partner(customer)
    share_bundle = build_partner_share_bundle(request, partner) if partner else None
    codes = list(
        DiscountCode.objects.filter(attributed_partner=partner).order_by("code")
    ) if partner else []
    commissions = list(
        PromotionCommissionLedger.objects.filter(partner=partner).order_by("-created_at")
    ) if partner else []
    commission_total = _money(
        PromotionCommissionLedger.objects.filter(
            partner=partner,
            status=PromotionCommissionLedger.LedgerStatus.EARNED,
        ).aggregate(total=Sum("commission_amount"))["total"]
        if partner
        else 0
    )
    revenue_total = _money(
        PromotionCommissionLedger.objects.filter(
            partner=partner,
            status=PromotionCommissionLedger.LedgerStatus.EARNED,
        ).aggregate(total=Sum("revenue_attributed"))["total"]
        if partner
        else 0
    )
    leaderboard = []
    for row in (
        PromotionCommissionLedger.objects.filter(status=PromotionCommissionLedger.LedgerStatus.EARNED)
        .values("partner__name")
        .annotate(
            revenue=Sum("revenue_attributed"),
            commission=Sum("commission_amount"),
        )
        .order_by("-revenue")[:10]
    ):
        leaderboard.append(
            {
                "name": row["partner__name"] or "Unknown partner",
                "revenue": _money(row["revenue"]),
                "commission": _money(row["commission"]),
            }
        )
    return {
        "partner": partner,
        "share": share_bundle,
        "codes": codes,
        "commissions": commissions,
        "commission_total": commission_total,
        "revenue_total": revenue_total,
        "leaderboard": leaderboard,
    }
