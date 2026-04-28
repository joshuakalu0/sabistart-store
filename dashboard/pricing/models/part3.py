"""
pricing/models_part3.py — Gift Cards (Section 6) + Tax Engine (Section 7)
"""

import uuid
import secrets
import string
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dashboard.settings.models import MixIdAndTimeModel, ActivatableModel, IduuidModel
from public.userauth.models import Customer


# ─────────────────────────────────────────────────────────────
# SECTION 6 — GIFT CARDS
# ─────────────────────────────────────────────────────────────

class GiftCardTemplate(MixIdAndTimeModel):
    """
    A visual/design template for gift cards.
    Templates define the appearance, default denominations,
    and configuration for gift cards issued from this template.

    A single store can have multiple templates:
      - "Birthday Gift Card" (pastel design, $25/$50/$100)
      - "Wedding Registry" (elegant design, custom amounts)
      - "Corporate Bulk Gift" (company branded, bulk pricing)
    """

    class IssuanceType(models.TextChoices):
        SINGLE_USE = "single_use", _("Single Use (one order per card)")
        MULTI_USE = "multi_use", _(
            "Multi-Use (balance-based, use until exhausted)")
        SUBSCRIPTION = "subscription", _(
            "Subscription Credit (monthly recurring)")

    name = models.CharField(_("Template Name"), max_length=255)
    description = models.TextField(_("Description"), blank=True)
    image = models.ImageField(
        _("Card Image"),
        upload_to="gift_cards/templates/",
        null=True,
        blank=True,
        help_text=_(
            "Visual design displayed in the gift card email and order details."),
    )
    background_color = models.CharField(
        _("Background Color (hex)"),
        max_length=7,
        default="#FFFFFF",
        validators=[RegexValidator(regex=r"^#[0-9A-Fa-f]{6}$")],
    )
    text_color = models.CharField(
        _("Text Color (hex)"),
        max_length=7,
        default="#000000",
        validators=[RegexValidator(regex=r"^#[0-9A-Fa-f]{6}$")],
    )

    # ── Denominations ──
    preset_amounts = models.JSONField(
        _("Preset Denominations"),
        default=list,
        blank=True,
        help_text=_(
            "e.g. [10, 25, 50, 100, 200]. Used for product page selector."),
    )
    allow_custom_amount = models.BooleanField(
        _("Allow Custom Amount"),
        default=True,
    )
    minimum_amount = models.DecimalField(
        _("Minimum Amount"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    maximum_amount = models.DecimalField(
        _("Maximum Amount"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("1000.00"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    currency = models.CharField(_("Currency"), max_length=3, default="USD")

    # ── Configuration ──
    issuance_type = models.CharField(
        _("Issuance Type"),
        max_length=15,
        choices=IssuanceType.choices,
        default=IssuanceType.MULTI_USE,
    )
    validity_days = models.PositiveIntegerField(
        _("Validity (days)"),
        null=True,
        blank=True,
        help_text=_("Days from issuance until expiry. Null = no expiry."),
    )
    is_transferable = models.BooleanField(
        _("Transferable"),
        default=True,
        help_text=_("Can the recipient forward the card code to someone else."),
    )
    is_active = models.BooleanField(_("Active"), default=True)
    is_physical = models.BooleanField(
        _("Physical Card"),
        default=False,
        help_text=_("True for physical cards mailed to the recipient."),
    )

    # ── Email template ──
    email_subject = models.CharField(
        _("Gift Email Subject"),
        max_length=500,
        default="You've received a gift card!",
    )
    email_body_template = models.TextField(
        _("Gift Email Body Template"),
        blank=True,
        help_text=_(
            "Jinja2 template. Available vars: "
            "{{ recipient_name }}, {{ sender_name }}, {{ amount }}, "
            "{{ code }}, {{ message }}, {{ expiry_date }}"
        ),
    )

    class Meta:
        verbose_name = _("Gift Card Template")
        verbose_name_plural = _("Gift Card Templates")
        ordering = ["name"]

    def __str__(self):
        return self.name


class GiftCard(MixIdAndTimeModel):
    """
    A single issued gift card with a unique code and a balance.

    The `balance` field is the LIVE current balance.
    All changes to balance MUST go through GiftCardTransaction.adjust().
    Never edit balance directly.

    Gift card lifecycle:
      ACTIVE    → Can be used at checkout
      REDEEMED  → Balance is 0 (fully spent)
      EXPIRED   → Past expiry date
      DISABLED  → Manually deactivated by staff
      PENDING   → Issued but not yet delivered to recipient

    Gift cards can be:
      1. Purchased as a product (customer buys for someone else)
      2. Issued manually by staff (compensation, refund, promotion)
      3. Issued automatically as a refund alternative
    """

    class GiftCardStatus(models.TextChoices):
        PENDING = "pending", _("Pending Delivery")
        ACTIVE = "active", _("Active — Has Balance")
        REDEEMED = "redeemed", _("Fully Redeemed (balance = 0)")
        EXPIRED = "expired", _("Expired")
        DISABLED = "disabled", _("Disabled by Staff")

    class IssuanceReason(models.TextChoices):
        PURCHASED = "purchased", _("Purchased by Customer")
        MANUAL_STAFF = "manual_staff", _("Manually Issued by Staff")
        REFUND = "refund", _("Issued as Refund Alternative")
        COMPENSATION = "compensation", _("Customer Compensation")
        PROMOTION = "promotion", _("Promotional Giveaway")
        LOYALTY = "loyalty", _("Loyalty Reward")
        BULK = "bulk", _("Bulk Corporate Issuance")

    template = models.ForeignKey(
        GiftCardTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="issued_cards",
        verbose_name=_("Template"),
    )

    # ── Code ──
    code = models.CharField(
        _("Gift Card Code"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_("Unique redemption code. Auto-generated if blank."),
    )
    masked_code = models.CharField(
        _("Masked Code"),
        max_length=50,
        blank=True,
        help_text=_(
            "e.g. 'XXXX-XXXX-XXXX-1234' — last 4 chars visible for display."),
    )

    # ── Balance ──
    initial_value = models.DecimalField(
        _("Initial Value"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_(
            "Value when the card was issued. Never changes post-issuance."),
    )
    balance = models.DecimalField(
        _("Current Balance"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "LIVE current balance. Do NOT edit directly. "
            "Use GiftCardTransaction.adjust() to modify."
        ),
    )
    currency = models.CharField(_("Currency"), max_length=3, default="USD")

    # ── Status ──
    status = models.CharField(
        _("Status"),
        max_length=15,
        choices=GiftCardStatus.choices,
        default=GiftCardStatus.PENDING,
        db_index=True,
    )

    # ── Validity ──
    issued_at = models.DateTimeField(
        _("Issued At"),
        default=timezone.now,
        db_index=True,
    )
    expires_at = models.DateTimeField(
        _("Expires At"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Null = never expires."),
    )
    activated_at = models.DateTimeField(
        _("Activated At"),
        null=True,
        blank=True,
    )
    last_used_at = models.DateTimeField(
        _("Last Used At"), null=True, blank=True)
    fully_redeemed_at = models.DateTimeField(
        _("Fully Redeemed At"), null=True, blank=True)

    # ── Issuance ──
    issuance_reason = models.CharField(
        _("Issuance Reason"),
        max_length=20,
        choices=IssuanceReason.choices,
        default=IssuanceReason.PURCHASED,
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="issued_gift_cards",
        verbose_name=_("Issued By (Staff)"),
    )
    purchase_order_id = models.UUIDField(
        _("Purchase Order ID"),
        null=True,
        blank=True,
        help_text=_("FK-less ref to orders.Order that purchased this card."),
    )

    # ── Recipient ──
    recipient_email = models.EmailField(_("Recipient Email"), blank=True)
    recipient_name = models.CharField(
        _("Recipient Name"), max_length=255, blank=True)
    sender_name = models.CharField(
        _("Sender Name"), max_length=255, blank=True)
    gift_message = models.TextField(_("Gift Message"), blank=True)
    delivery_method = models.CharField(
        _("Delivery Method"),
        max_length=15,
        choices=[("email", _("Email")), ("sms", _("SMS")),
                 ("physical", _("Physical Mail"))],
        default="email",
    )
    delivered_at = models.DateTimeField(
        _("Delivered At"), null=True, blank=True)
    delivery_failed = models.BooleanField(_("Delivery Failed"), default=False)

    # ── Owner (who currently holds the card) ──
    owner = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gift_cards",
        verbose_name=_("Card Owner (Customer)"),
        help_text=_(
            "The customer who currently has this card in their account."),
    )

    # ── Usage settings ──
    is_transferable = models.BooleanField(_("Transferable"), default=True)
    note = models.TextField(_("Internal Note"), blank=True)
    disable_reason = models.CharField(
        _("Disable Reason"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("Gift Card")
        verbose_name_plural = _("Gift Cards")
        ordering = ["-issued_at"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["owner"]),
            models.Index(fields=["recipient_email"]),
            models.Index(fields=["purchase_order_id"]),
        ]

    def __str__(self):
        return f"Gift Card {self.masked_code or self.code} — {self.currency} {self.balance}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        if not self.masked_code and self.code:
            self.masked_code = self._mask_code(self.code)
        super().save(*args, **kwargs)

    # ── Class methods ──

    @staticmethod
    def _generate_code(length: int = 16, segment_size: int = 4) -> str:
        """
        Generate a secure, URL-safe gift card code.
        Format: XXXX-XXXX-XXXX-XXXX (uppercase alphanumeric, no ambiguous chars)
        """
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # No I, O, 0, 1 to avoid confusion
        code_chars = [secrets.choice(alphabet) for _ in range(length)]
        segments = [
            "".join(code_chars[i:i + segment_size])
            for i in range(0, length, segment_size)
        ]
        return "-".join(segments)

    @staticmethod
    def _mask_code(code: str) -> str:
        """Mask all but the last 4 characters of each segment."""
        parts = code.split("-")
        masked_parts = ["X" * len(p) for p in parts[:-1]] + [parts[-1]]
        return "-".join(masked_parts)

    # ── Properties ──

    @property
    def is_usable(self) -> bool:
        """True if the card can be applied at checkout right now."""
        if self.status != self.GiftCardStatus.ACTIVE:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.balance <= 0:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < timezone.now()

    @property
    def percent_used(self) -> float:
        if not self.initial_value:
            return 0.0
        used = self.initial_value - self.balance
        return round(float(used / self.initial_value) * 100, 1)

    # ── Lifecycle methods ──

    def activate(self):
        """Activate a PENDING gift card and set its initial balance."""
        if self.status != self.GiftCardStatus.PENDING:
            raise ValueError(
                f"Cannot activate a card with status '{self.status}'.")
        self.status = self.GiftCardStatus.ACTIVE
        self.balance = self.initial_value
        self.activated_at = timezone.now()
        self.save(update_fields=["status", "balance",
                  "activated_at", "updated_at"])

    def disable(self, reason: str = "", actor=None):
        """Disable a gift card (staff action)."""
        self.status = self.GiftCardStatus.DISABLED
        self.disable_reason = reason
        self.save(update_fields=["status", "disable_reason", "updated_at"])

    @transaction.atomic
    def redeem(self, amount: Decimal, order_id=None, order_number: str = "", actor=None):
        """
        Deduct an amount from the gift card balance at checkout.
        Creates a DEBIT transaction record.

        Args:
            amount: Amount to deduct (must be ≤ balance).
            order_id: UUID of the order being paid.
            order_number: Human-readable order number.
            actor: Customer or system performing the redemption.

        Returns:
            GiftCardTransaction: The created transaction.

        Raises:
            ValueError: If card is not usable or amount exceeds balance.
        """
        if not self.is_usable:
            raise ValueError(f"Gift card {self.code} is not usable.")

        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if amount <= 0:
            raise ValueError("Redemption amount must be greater than zero.")

        if amount > self.balance:
            raise ValueError(
                f"Redemption amount {amount} exceeds card balance {self.balance}."
            )

        self_locked = GiftCard.objects.select_for_update().get(pk=self.pk)
        self_locked.balance -= amount
        self_locked.last_used_at = timezone.now()

        if self_locked.balance == 0:
            self_locked.status = self.GiftCardStatus.REDEEMED
            self_locked.fully_redeemed_at = timezone.now()

        self_locked.save(update_fields=[
            "balance", "status", "last_used_at", "fully_redeemed_at", "updated_at"
        ])

        txn = GiftCardTransaction.objects.create(
            gift_card=self,
            transaction_type=GiftCardTransaction.TransactionType.DEBIT,
            amount=-amount,
            balance_before=self_locked.balance + amount,
            balance_after=self_locked.balance,
            order_id=order_id,
            order_number=order_number,
            note=f"Redeemed at checkout for order {order_number}",
        )

        # Reflect changes on self
        self.balance = self_locked.balance
        self.status = self_locked.status

        return txn

    @transaction.atomic
    def refund(self, amount: Decimal, reason: str = "", actor=None):
        """
        Credit an amount back to the gift card (e.g. order refund).
        Creates a CREDIT transaction record.
        """
        if self.status == self.GiftCardStatus.DISABLED:
            raise ValueError("Cannot refund to a disabled gift card.")

        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if amount <= 0:
            raise ValueError("Refund amount must be greater than zero.")

        self_locked = GiftCard.objects.select_for_update().get(pk=self.pk)
        self_locked.balance += amount
        if self_locked.status == self.GiftCardStatus.REDEEMED:
            self_locked.status = self.GiftCardStatus.ACTIVE
            self_locked.fully_redeemed_at = None

        self_locked.save(update_fields=[
            "balance", "status", "fully_redeemed_at", "updated_at"
        ])

        txn = GiftCardTransaction.objects.create(
            gift_card=self,
            transaction_type=GiftCardTransaction.TransactionType.CREDIT,
            amount=amount,
            balance_before=self_locked.balance - amount,
            balance_after=self_locked.balance,
            note=reason or "Refund credited to gift card",
        )
        self.balance = self_locked.balance
        self.status = self_locked.status
        return txn


class GiftCardTransaction(IduuidModel):
    """
    IMMUTABLE append-only ledger of every balance change on a GiftCard.
    Never UPDATE or DELETE. Only INSERT.

    Transaction types:
      CREDIT   → Balance increased (issued, refunded, adjusted up)
      DEBIT    → Balance decreased (redeemed at checkout, adjusted down)
      VOID     → A previous debit was voided (order cancelled before fulfillment)
      EXPIRE   → Balance zeroed at expiry date (by scheduled task)
      TRANSFER → Balance moved to another gift card
    """

    class TransactionType(models.TextChoices):
        CREDIT = "credit", _("Credit (balance added)")
        DEBIT = "debit", _("Debit (balance used)")
        VOID = "void", _("Void (debit reversed)")
        EXPIRE = "expire", _("Expire (balance zeroed)")
        TRANSFER_OUT = "transfer_out", _("Transfer Out")
        TRANSFER_IN = "transfer_in", _("Transfer In")
        ADJUSTMENT = "adjustment", _("Manual Adjustment by Staff")

    gift_card = models.ForeignKey(
        GiftCard,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name=_("Gift Card"),
    )
    transaction_type = models.CharField(
        _("Transaction Type"),
        max_length=15,
        choices=TransactionType.choices,
        db_index=True,
    )
    amount = models.DecimalField(
        _("Amount"),
        max_digits=14,
        decimal_places=2,
        help_text=_(
            "Signed amount. Positive = credit (balance increased). "
            "Negative = debit (balance decreased)."
        ),
    )
    balance_before = models.DecimalField(
        _("Balance Before"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    balance_after = models.DecimalField(
        _("Balance After"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    # ── References ──
    order_id = models.UUIDField(
        _("Order ID"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("FK-less ref to the order this transaction is related to."),
    )
    order_number = models.CharField(
        _("Order Number"), max_length=50, blank=True)
    related_card = models.ForeignKey(
        GiftCard,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="related_transactions",
        verbose_name=_("Related Gift Card"),
        help_text=_("For TRANSFER transactions: the other card involved."),
    )

    # ── Actor ──
    # performed_by = models.ForeignKey(
    #     settings.AUTH_USER_MODEL,
    #     null=True,
    #     blank=True,
    #     on_delete=models.SET_NULL,
    #     related_name="gift_card_transactions",
    #     verbose_name=_("Performed By"),
    #     help_text=_("Null = system-triggered (checkout, expiry task)."),
    # )
    note = models.TextField(_("Note"), blank=True)

    # ── Immutable timestamp ──
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Gift Card Transaction")
        verbose_name_plural = _("Gift Card Transactions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["gift_card", "-created_at"]),
            models.Index(fields=["transaction_type"]),
            models.Index(fields=["order_id"]),
        ]

    def __str__(self):
        sign = "+" if self.amount > 0 else ""
        return (
            f"{self.gift_card.masked_code or self.gift_card.code} "
            f"{self.transaction_type}: {sign}{self.amount} "
            f"(balance: {self.balance_before} → {self.balance_after})"
        )


# ─────────────────────────────────────────────────────────────
# SECTION 7 — TAX ENGINE
# ─────────────────────────────────────────────────────────────

class TaxCategory(MixIdAndTimeModel):
    """
    A named classification for products that determines which
    tax rates apply to them in different zones.

    Common tax categories:
      - Standard Rate (most physical goods)
      - Reduced Rate (food, books, children's clothing)
      - Zero Rate (exports, unprocessed food in some jurisdictions)
      - Exempt (financial services, medical devices)
      - Digital Goods (software, ebooks — different VAT rules in EU)
      - Luxury Goods (extra tax in some jurisdictions)

    Products reference a TaxCategory. Tax rates are defined per
    TaxCategory + TaxZone combination in TaxRate.
    """

    name = models.CharField(
        _("Category Name"),
        max_length=100,
        help_text=_("e.g. 'Standard Rate', 'Food', 'Digital Goods'"),
    )
    code = models.CharField(
        _("Code"),
        max_length=50,
        unique=True,
        help_text=_(
            "Internal identifier. e.g. 'STANDARD', 'REDUCED', 'ZERO', 'DIGITAL'"),
    )
    description = models.TextField(_("Description"), blank=True)
    is_default = models.BooleanField(
        _("Default Category"),
        default=False,
        help_text=_(
            "Products without an explicit tax category use this one. "
            "Only one category can be default."
        ),
    )
    is_taxable = models.BooleanField(
        _("Taxable"),
        default=True,
        help_text=_(
            "If False, products in this category are always tax-exempt."),
    )
    sort_order = models.PositiveSmallIntegerField(_("Sort Order"), default=0)

    class Meta:
        verbose_name = _("Tax Category")
        verbose_name_plural = _("Tax Categories")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.is_default:
            TaxCategory.objects.exclude(pk=self.pk).filter(
                is_default=True
            ).update(is_default=False)
        super().save(*args, **kwargs)


class TaxZone(MixIdAndTimeModel):
    """
    A geographic region with a distinct tax configuration.

    Zones are matched against the shipping (or billing, depending on config)
    address at checkout. The most specific matching zone wins.

    Zone specificity (most → least specific):
      Postal code → City → State/Province → Country → Global fallback

    Examples:
      - "Nigeria" (country-level, 7.5% VAT on standard goods)
      - "California, US" (state-level, 10.25% combined rate)
      - "European Union" (multi-country zone, handles EU VAT OSS rules)
      - "Lagos, NG" (city-level if different from national rate)
    """

    class ZoneType(models.TextChoices):
        COUNTRY = "country", _("Country")
        STATE = "state", _("State / Province / Region")
        CITY = "city", _("City")
        POSTAL_CODE = "postal_code", _("Postal Code Range")
        MULTI_COUNTRY = "multi_country", _("Multi-Country Group")
        GLOBAL = "global", _("Global Fallback")

    name = models.CharField(
        _("Zone Name"),
        max_length=255,
        help_text=_("e.g. 'Nigeria', 'California', 'EU VAT Zone'"),
    )
    code = models.CharField(
        _("Zone Code"),
        max_length=50,
        unique=True,
        help_text=_("e.g. 'NG', 'US-CA', 'EU', 'GLOBAL'"),
    )
    zone_type = models.CharField(
        _("Zone Type"),
        max_length=15,
        choices=ZoneType.choices,
        default=ZoneType.COUNTRY,
    )

    # ── Geographic targeting ──
    countries = models.JSONField(
        _("Countries"),
        default=list,
        blank=True,
        help_text=_(
            "ISO 3166-1 alpha-2 codes. e.g. ['NG', 'GH', 'KE'] for West/East Africa. "
            "Used for COUNTRY and MULTI_COUNTRY zone types."
        ),
    )
    states = models.JSONField(
        _("States / Provinces"),
        default=list,
        blank=True,
        help_text=_(
            "State/province codes within the target country. "
            "e.g. ['CA', 'NY', 'TX'] for US states."
        ),
    )
    cities = models.JSONField(
        _("Cities"),
        default=list,
        blank=True,
    )
    postal_codes = models.JSONField(
        _("Postal Codes"),
        default=list,
        blank=True,
        help_text=_(
            "Exact codes or prefixes. e.g. ['10001', '10002', '100*']"),
    )
    exclude_countries = models.JSONField(
        _("Excluded Countries"),
        default=list,
        blank=True,
        help_text=_("Countries explicitly excluded from a MULTI_COUNTRY zone."),
    )

    # ── Tax address basis ──
    use_billing_address = models.BooleanField(
        _("Use Billing Address for Tax"),
        default=False,
        help_text=_(
            "If True, tax zone matching uses billing address instead of shipping address. "
            "Required by some jurisdictions (e.g. digital goods in EU VAT OSS)."
        ),
    )

    # ── Registration ──
    tax_registration_number = models.CharField(
        _("Tax Registration Number"),
        max_length=100,
        blank=True,
        help_text=_(
            "The store's tax registration number for this zone. "
            "Displayed on invoices. e.g. VAT number, FIRS TIN."
        ),
    )

    # ── Status ──
    is_active = models.BooleanField(_("Active"), default=True, db_index=True)
    priority = models.PositiveIntegerField(
        _("Matching Priority"),
        default=0,
        help_text=_(
            "When multiple zones match an address, the one with the highest "
            "priority wins. Postal code zones should have the highest priority."
        ),
    )

    class Meta:
        verbose_name = _("Tax Zone")
        verbose_name_plural = _("Tax Zones")
        ordering = ["-priority", "name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["zone_type", "is_active"]),
            models.Index(fields=["priority"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code}) [{self.zone_type}]"

    def matches_address(self, country: str, state: str = "", city: str = "", postal: str = "") -> bool:
        """
        Check whether a given address falls within this tax zone.

        Returns:
            bool: True if this zone applies to the given address.
        """
        if not self.is_active:
            return False

        if self.zone_type == self.ZoneType.GLOBAL:
            return True

        if country in self.exclude_countries:
            return False

        if self.zone_type in (self.ZoneType.COUNTRY, self.ZoneType.MULTI_COUNTRY):
            return country in self.countries

        if self.zone_type == self.ZoneType.STATE:
            return country in self.countries and (not self.states or state in self.states)

        if self.zone_type == self.ZoneType.CITY:
            return (
                country in self.countries
                and (not self.states or state in self.states)
                and (not self.cities or city in self.cities)
            )

        if self.zone_type == self.ZoneType.POSTAL_CODE:
            for pc_pattern in self.postal_codes:
                if pc_pattern.endswith("*"):
                    if postal.startswith(pc_pattern[:-1]):
                        return True
                elif postal == pc_pattern:
                    return True
            return False

        return False


class TaxRate(MixIdAndTimeModel, ActivatableModel):
    """
    The actual tax percentage applied to a TaxCategory within a TaxZone.

    One TaxRate = one TaxZone + one TaxCategory + one percentage.

    A single order can accumulate multiple TaxRate records:
      - Standard goods in Nigeria → 7.5% (federal VAT)
      - A state surcharge → 1.5% (hypothetical state tax)
      → Two TaxRate records, both applied

    Compound tax:
      is_compound=True means this rate is applied ON TOP of the base
      (tax-on-tax). Used in some Canadian province tax structures.

    Tax-inclusive pricing:
      is_included_in_price=True means the product's price already
      includes this tax. The displayed price doesn't change, but
      the tax amount is extracted and shown on the invoice.
    """

    class TaxType(models.TextChoices):
        VAT = "vat", _("VAT (Value Added Tax)")
        GST = "gst", _("GST (Goods and Services Tax)")
        SALES_TAX = "sales_tax", _("Sales Tax")
        EXCISE = "excise", _("Excise Duty")
        CUSTOMS = "customs", _("Customs / Import Duty")
        WITHHOLDING = "withholding", _("Withholding Tax")
        OTHER = "other", _("Other")

    tax_zone = models.ForeignKey(
        TaxZone,
        on_delete=models.CASCADE,
        related_name="tax_rates",
        verbose_name=_("Tax Zone"),
    )
    tax_category = models.ForeignKey(
        TaxCategory,
        on_delete=models.CASCADE,
        related_name="tax_rates",
        verbose_name=_("Tax Category"),
        help_text=_(
            "The product classification this rate applies to within the zone."),
    )

    # ── Rate ──
    name = models.CharField(
        _("Tax Name"),
        max_length=255,
        help_text=_(
            "Display name shown on invoices and receipts. e.g. 'VAT (7.5%)', 'GST'"),
    )
    tax_type = models.CharField(
        _("Tax Type"),
        max_length=15,
        choices=TaxType.choices,
        default=TaxType.VAT,
    )
    rate = models.DecimalField(
        _("Rate (%)"),
        max_digits=7,
        decimal_places=4,
        validators=[MinValueValidator(
            Decimal("0.0000")), MaxValueValidator(Decimal("100.0000"))],
        help_text=_("e.g. 7.5000 for 7.5% VAT. 0.0000 for zero-rated."),
    )

    # ── Tax behaviour flags ──
    is_included_in_price = models.BooleanField(
        _("Included in Price"),
        default=False,
        help_text=_(
            "If True, product prices are tax-inclusive. "
            "Tax is extracted from the price (not added on top)."
        ),
    )
    is_compound = models.BooleanField(
        _("Compound Tax"),
        default=False,
        help_text=_(
            "If True, this tax is applied on top of the subtotal + other taxes. "
            "Used in some Canadian provinces (PST applied after GST)."
        ),
    )
    applies_to_shipping = models.BooleanField(
        _("Applies to Shipping"),
        default=False,
        help_text=_(
            "If True, this tax rate is also applied to the shipping cost."),
    )
    applies_to_digital_goods = models.BooleanField(
        _("Applies to Digital Goods"),
        default=True,
    )

    # ── Thresholds ──
    threshold_amount = models.DecimalField(
        _("Threshold Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "This rate only activates when the order total exceeds this amount. "
            "Used for luxury goods thresholds."
        ),
    )
    de_minimis_threshold = models.DecimalField(
        _("De Minimis Threshold"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Tax is not collected if the order total is below this amount. "
            "Used for import duty de minimis rules."
        ),
    )

    # ── Authority ──
    tax_authority = models.CharField(
        _("Tax Authority"),
        max_length=255,
        blank=True,
        help_text=_(
            "e.g. 'FIRS' (Nigeria), 'HMRC' (UK), 'IRS' (US), 'ATO' (Australia)"),
    )
    tax_code = models.CharField(
        _("Tax Code"),
        max_length=100,
        blank=True,
        help_text=_(
            "Official tax code from the authority. Used in tax filing reports."),
    )

    # ── Priority ──
    priority = models.PositiveSmallIntegerField(
        _("Priority"),
        default=0,
        help_text=_(
            "Order in which this rate is applied. "
            "Lower = applied first (important for compound taxes)."
        ),
    )

    class Meta:
        verbose_name = _("Tax Rate")
        verbose_name_plural = _("Tax Rates")
        unique_together = [("tax_zone", "tax_category")]
        ordering = ["tax_zone", "priority", "tax_category"]
        indexes = [
            models.Index(fields=["tax_zone", "tax_category"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["rate"]),
        ]

    def __str__(self):
        return (
            f"{self.name} — {self.rate}% "
            f"({self.tax_zone.code} × {self.tax_category.code})"
        )

    def compute_tax_amount(
        self,
        taxable_amount: Decimal,
        base_tax_already_applied: Decimal = Decimal("0.00"),
    ) -> Decimal:
        """
        Calculate the tax amount for a given taxable base.

        For standard (non-compound) taxes:
            tax = taxable_amount × rate

        For compound taxes:
            tax = (taxable_amount + base_tax_already_applied) × rate

        For tax-inclusive prices:
            tax = taxable_amount × rate / (1 + rate)

        Args:
            taxable_amount: The pre-tax amount (subtotal or line total).
            base_tax_already_applied: Sum of non-compound taxes already calculated
                                       (used only when is_compound=True).

        Returns:
            Decimal: The tax amount to charge.
        """
        TWO_PLACES = Decimal("0.01")
        rate_decimal = self.rate / Decimal("100")

        if self.is_included_in_price:
            # Extract tax from inclusive price
            tax = taxable_amount * rate_decimal / (Decimal("1") + rate_decimal)
        elif self.is_compound:
            # Apply on top of subtotal + all previous taxes
            base = taxable_amount + base_tax_already_applied
            tax = base * rate_decimal
        else:
            tax = taxable_amount * rate_decimal

        return tax.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    @property
    def rate_as_decimal(self) -> Decimal:
        """Rate expressed as a decimal fraction (e.g. 7.5% → 0.075)."""
        return self.rate / Decimal("100")
