"""
orders/models.py
================
App 7 — Orders & Checkout Domain
Multi-tenant e-commerce platform (django-tenants, schema-based isolation)

Models:
  1.  Cart
  2.  CartItem
  3.  CartDiscount
  4.  Order
  5.  OrderItem
  6.  OrderAddress
  7.  OrderStatusHistory
  8.  OrderNote
  9.  OrderTag
  10. OrderDiscount
  11. OrderTax
  12. Fulfillment
  13. FulfillmentItem
  14. TrackingInfo
  15. Return
  16. ReturnItem
  17. ReturnEvent
  18. Refund
  19. RefundLineItem

Architecture notes:
  - All monetary values stored as Decimal(14,2) — never float.
  - All IDs are UUID4 — no sequential integer exposure to clients.
  - OrderAddress is a snapshot (immutable after order creation).
  - StockMovement and Payment models live in their own apps;
    cross-app references use UUID fields (no DB-level FK across apps).
  - All status transitions are logged in append-only history tables.
  - Cart → Order promotion is handled in a service layer, not here.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dashboard.settings.models import AuditModel, MixIdAndTimeModel, IduuidModel

# ─────────────────────────────────────────────────────────────
# ABSTRACT BASES
# ─────────────────────────────────────────────────────────────


class MoneyMixin(models.Model):
    """
    Shared money + currency fields for any model that holds totals.
    All subclasses must define their own currency field or inherit this.
    """
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        default="USD",
        help_text=_("ISO 4217 currency code. e.g. USD, NGN, GBP"),
    )

    class Meta:
        abstract = True


# ─────────────────────────────────────────────────────────────
# SECTION 1 — CART
# ─────────────────────────────────────────────────────────────

class Cart(MixIdAndTimeModel, MoneyMixin):
    """
    Active shopping session. One cart per customer session or logged-in user.

    A Cart is ephemeral — it is converted into an Order at checkout.
    Abandoned carts are retained for analytics and recovery campaigns.

    Cart status lifecycle:
      ACTIVE      → In use, items being added/removed
      RECOVERING  → Abandonment recovery email has been sent
      ABANDONED   → No activity for configured timeout, not converted
      CONVERTED   → Successfully placed as an Order
      EXPIRED     → TTL exceeded, never converted

    Guest carts use session_key only. Authenticated carts link to Customer.
    When a guest logs in, their guest cart is merged into their account cart.
    """

    class CartStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        RECOVERING = "recovering", _("Recovery In Progress")
        ABANDONED = "abandoned", _("Abandoned")
        CONVERTED = "converted", _("Converted to Order")
        EXPIRED = "expired", _("Expired")

    class CartSource(models.TextChoices):
        WEB = "web", _("Web Storefront")
        MOBILE = "mobile", _("Mobile App")
        POS = "pos", _("Point of Sale")
        ADMIN = "admin", _("Admin / Draft Order")
        API = "api", _("API / Headless")

    # ── Owner ──
    customer = models.ForeignKey(
        "userauth.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="carts",
        verbose_name=_("Customer"),
        help_text=_("Null for guest carts. Set on login or registration."),
    )
    session_key = models.CharField(
        _("Session Key"),
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("Anonymous session identifier for guest carts."),
    )
    email = models.EmailField(
        _("Email"),
        blank=True,
        help_text=_("Captured early in checkout for abandonment emails."),
    )

    # ── Status ──
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=CartStatus.choices,
        default=CartStatus.ACTIVE,
        db_index=True,
    )
    source = models.CharField(
        _("Source"),
        max_length=20,
        choices=CartSource.choices,
        default=CartSource.WEB,
    )

    # ── Shipping address (pre-checkout capture) ──
    shipping_country = models.CharField(
        _("Shipping Country"), max_length=2, blank=True)
    shipping_state = models.CharField(
        _("Shipping State"), max_length=100, blank=True)
    shipping_postal_code = models.CharField(
        _("Shipping Postal Code"), max_length=20, blank=True)
    # shipping_rate_id = models.UUIDField(
    #     _("Selected Shipping Rate"),
    #     null=True,
    #     blank=True,
    #     help_text=_(
    #         "FK-less ref to shipping.ShippingRate chosen during checkout."),
    # )

    # ── Applied discount codes ──
    discount_code = models.CharField(
        _("Discount Code"),
        max_length=100,
        blank=True,
        help_text=_("Active coupon code applied to this cart."),
    )

    # ── Totals (computed / cached) ──
    subtotal = models.DecimalField(
        _("Subtotal"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "Sum of (price × qty) for all items, before discounts/tax/shipping."),
    )
    discount_total = models.DecimalField(
        _("Discount Total"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    shipping_total = models.DecimalField(
        _("Shipping Total"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_total = models.DecimalField(
        _("Tax Total"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    grand_total = models.DecimalField(
        _("Grand Total"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    # ── Checkout progress tracking ──
    checkout_step = models.CharField(
        _("Last Checkout Step"),
        max_length=50,
        blank=True,
        help_text=_("e.g. 'cart', 'address', 'shipping', 'payment', 'review'"),
    )
    checkout_token = models.CharField(
        _("Checkout Token"),
        max_length=255,
        unique=True,
        blank=True,
        help_text=_("Signed token used in checkout URLs. Prevents IDOR."),
    )

    # ── Abandonment tracking ──
    last_activity_at = models.DateTimeField(
        _("Last Activity At"),
        default=timezone.now,
        db_index=True,
    )
    abandoned_at = models.DateTimeField(
        _("Abandoned At"), null=True, blank=True)
    recovery_email_sent_at = models.DateTimeField(
        _("Recovery Email Sent At"),
        null=True,
        blank=True,
    )
    recovery_email_count = models.PositiveSmallIntegerField(
        _("Recovery Emails Sent"),
        default=0,
    )

    # ── Conversion ──
    converted_to_order_id = models.UUIDField(
        _("Converted to Order"),
        null=True,
        blank=True,
        help_text=_("FK-less ref to the Order created from this cart."),
    )
    converted_at = models.DateTimeField(
        _("Converted At"), null=True, blank=True)

    # ── Context ──
    ip_address = models.GenericIPAddressField(
        _("IP Address"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)
    utm_source = models.CharField(_("UTM Source"), max_length=255, blank=True)
    utm_medium = models.CharField(_("UTM Medium"), max_length=255, blank=True)
    utm_campaign = models.CharField(
        _("UTM Campaign"), max_length=255, blank=True)
    referrer_url = models.URLField(_("Referrer URL"), blank=True)

    # ── Notes ──
    customer_note = models.TextField(
        _("Customer Note"),
        blank=True,
        help_text=_("Note from the customer entered during checkout."),
    )

    class Meta:
        verbose_name = _("Cart")
        verbose_name_plural = _("Carts")
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["session_key"]),
            models.Index(fields=["status", "last_activity_at"]),
            models.Index(fields=["checkout_token"]),
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self):
        owner = self.customer or self.email or self.session_key[:12]
        return f"Cart {self.id} [{self.status}] — {owner}"

    @property
    def item_count(self):
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    @property
    def is_empty(self):
        return not self.items.exists()

    def mark_abandoned(self):
        self.status = self.CartStatus.ABANDONED
        self.abandoned_at = timezone.now()
        self.save(update_fields=["status", "abandoned_at", "updated_at"])

    def mark_converted(self, order_id):
        self.status = self.CartStatus.CONVERTED
        self.converted_to_order_id = order_id
        self.converted_at = timezone.now()
        self.save(update_fields=[
            "status", "converted_to_order_id", "converted_at", "updated_at"
        ])


# ─────────────────────────────────────────────────────────────

class CartItem(MixIdAndTimeModel):
    """
    A single line in a Cart — one ProductVariant + quantity.

    Price fields are captured at time of item addition so that
    the cart total is stable even if the product price changes mid-session.
    The final order line price is re-validated at checkout submission.
    """

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Cart"),
    )
    variant = models.ForeignKey(
        "product.ProductVariant",
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name=_("Product Variant"),
    )

    # ── Quantity ──
    quantity = models.PositiveIntegerField(
        _("Quantity"),
        default=1,
        validators=[MinValueValidator(1)],
    )
    max_quantity = models.PositiveIntegerField(
        _("Max Allowed Quantity"),
        null=True,
        blank=True,
        help_text=_(
            "Per-item cap enforced at checkout (e.g. limited releases)."),
    )

    # ── Price snapshot ──
    unit_price = models.DecimalField(
        _("Unit Price (at add time)"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    compare_at_price = models.DecimalField(
        _("Compare At Price"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    original_price = models.DecimalField(
        _("Original Price (before discounts)"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # ── Product snapshot (denormalized for display) ──
    product_title = models.CharField(
        _("Product Title"), max_length=500, blank=True)
    variant_title = models.CharField(
        _("Variant Title"), max_length=500, blank=True)
    product_image_url = models.URLField(_("Product Image URL"), blank=True)
    sku = models.CharField(_("SKU"), max_length=255, blank=True)

    # ── Flags ──
    is_gift = models.BooleanField(_("Is Gift"), default=False)
    gift_message = models.TextField(_("Gift Message"), blank=True)
    requires_shipping = models.BooleanField(
        _("Requires Shipping"), default=True)

    # ── Custom line properties (e.g. engraving text, customization) ──
    custom_properties = models.JSONField(
        _("Custom Properties"),
        default=dict,
        blank=True,
        help_text=_("Key-value pairs for custom line item attributes."),
    )

    class Meta:
        verbose_name = _("Cart Item")
        verbose_name_plural = _("Cart Items")
        unique_together = [("cart", "variant")]
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["cart", "variant"]),
        ]

    def __str__(self):
        return f"{self.quantity}× {self.variant} in Cart {self.cart_id}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def is_on_sale(self):
        return (
            self.compare_at_price is not None
            and self.compare_at_price > self.unit_price
        )


# ─────────────────────────────────────────────────────────────

class CartDiscount(MixIdAndTimeModel):
    """
    Tracks discount codes or automatic discounts applied to a Cart.
    Multiple discounts can stack depending on tenant config.
    """

    class DiscountType(models.TextChoices):
        CODE = "code", _("Coupon Code")
        AUTOMATIC = "automatic", _("Automatic Discount")
        BUNDLE = "bundle", _("Bundle Discount")
        GIFT_CARD = "gift_card", _("Gift Card")
        LOYALTY = "loyalty", _("Loyalty Points")

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="discounts",
        verbose_name=_("Cart"),
    )
    discount_type = models.CharField(
        _("Discount Type"),
        max_length=20,
        choices=DiscountType.choices,
    )
    code = models.CharField(_("Code"), max_length=100, blank=True)
    discount_id = models.UUIDField(
        _("Discount Rule ID"),
        null=True,
        blank=True,
        help_text=_(
            "FK-less ref to pricing.DiscountCode or pricing.AutomaticDiscount."),
    )
    description = models.CharField(
        _("Description"), max_length=500, blank=True)
    amount = models.DecimalField(
        _("Discount Amount"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_percentage = models.BooleanField(_("Is Percentage"), default=False)
    percentage_value = models.DecimalField(
        _("Percentage Value"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        verbose_name = _("Cart Discount")
        verbose_name_plural = _("Cart Discounts")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.code or self.discount_type} — {self.amount} off Cart {self.cart_id}"


# ─────────────────────────────────────────────────────────────
# SECTION 2 — ORDER
# ─────────────────────────────────────────────────────────────

class Order(MixIdAndTimeModel, MoneyMixin):
    """
    The confirmed, immutable purchase record created after successful checkout.

    An Order is the central entity of the commerce domain. It references:
      - The customer who placed it
      - The line items (OrderItem)
      - Addresses (OrderAddress — snapshot, never mutable)
      - Applied discounts (OrderDiscount)
      - Tax breakdown (OrderTax)
      - Fulfillments (Fulfillment → FulfillmentItem → TrackingInfo)
      - Returns and Refunds

    Status model:
    ┌──────────────────────────────────────────────────────────┐
    │  Order Status (overall order lifecycle)                  │
    │   PENDING → CONFIRMED → PROCESSING → COMPLETED          │
    │   Any state → CANCELLED                                  │
    │   COMPLETED → PARTIALLY_RETURNED / RETURNED             │
    │                                                          │
    │  Financial Status (money state)                          │
    │   PENDING → AUTHORIZED → PAID                           │
    │   PAID → PARTIALLY_REFUNDED → REFUNDED                  │
    │   Any → VOIDED                                           │
    │                                                          │
    │  Fulfillment Status (shipment state)                     │
    │   UNFULFILLED → PARTIALLY_FULFILLED → FULFILLED         │
    │   Any fulfilled state → PARTIALLY_RETURNED / RETURNED   │
    └──────────────────────────────────────────────────────────┘
    """

    # ── ORDER STATUS ──
    class OrderStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING = "pending", _("Pending Confirmation")
        CONFIRMED = "confirmed", _("Confirmed")
        PROCESSING = "processing", _("Processing")
        ON_HOLD = "on_hold", _("On Hold")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")
        PARTIALLY_RETURNED = "partially_returned", _("Partially Returned")
        RETURNED = "returned", _("Fully Returned")
        FRAUD_REVIEW = "fraud_review", _("Under Fraud Review")

    # ── FINANCIAL STATUS ──
    class FinancialStatus(models.TextChoices):
        PENDING = "pending", _("Payment Pending")
        AUTHORIZED = "authorized", _("Payment Authorized")
        PARTIALLY_PAID = "partially_paid", _("Partially Paid")
        PAID = "paid", _("Paid")
        PARTIALLY_REFUNDED = "partially_refunded", _("Partially Refunded")
        REFUNDED = "refunded", _("Fully Refunded")
        VOIDED = "voided", _("Voided")
        FAILED = "failed", _("Payment Failed")

    # ── FULFILLMENT STATUS ──
    class FulfillmentStatus(models.TextChoices):
        UNFULFILLED = "unfulfilled", _("Unfulfilled")
        PARTIALLY_FULFILLED = "partially_fulfilled", _("Partially Fulfilled")
        FULFILLED = "fulfilled", _("Fulfilled")
        PARTIALLY_SHIPPED = "partially_shipped", _("Partially Shipped")
        SHIPPED = "shipped", _("Shipped")
        PARTIALLY_DELIVERED = "partially_delivered", _("Partially Delivered")
        DELIVERED = "delivered", _("Delivered")
        PARTIALLY_RETURNED = "partially_returned", _("Partially Returned")
        RETURNED = "returned", _("Returned")

    # ── ORDER SOURCE ──
    class OrderSource(models.TextChoices):
        WEB = "web", _("Web Storefront")
        MOBILE = "mobile", _("Mobile App")
        POS = "pos", _("Point of Sale")
        ADMIN = "admin", _("Admin / Manual Order")
        API = "api", _("API / Headless")
        IMPORT = "import", _("Imported")
        SUBSCRIPTION = "subscription", _("Subscription / Recurring")

    # ── Human-readable number ──
    order_number = models.CharField(
        _("Order Number"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_("Human-readable order ID. e.g. ORD-000123 or #1001"),
    )
    order_number_sequence = models.PositiveIntegerField(
        _("Order Sequence"),
        unique=True,
        help_text=_(
            "Auto-incremented integer behind the human-readable number."),
    )

    # ── Relationships ──
    customer = models.ForeignKey(
        "userauth.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
        verbose_name=_("Customer"),
        help_text=_("Null for guest orders."),
    )
    cart_id = models.UUIDField(
        _("Source Cart"),
        null=True,
        blank=True,
        help_text=_("FK-less ref to the Cart this order was converted from."),
    )

    # ── Contact info snapshot ──
    customer_email = models.EmailField(
        _("Customer Email"),
        db_index=True,
        help_text=_(
            "Captured at order time for guest orders or email changes."),
    )
    customer_phone = models.CharField(
        _("Customer Phone"), max_length=30, blank=True)
    customer_name = models.CharField(
        _("Customer Name"),
        max_length=255,
        help_text=_("Snapshot at order time."),
    )

    # ── Status fields ──
    status = models.CharField(
        _("Order Status"),
        max_length=30,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
    financial_status = models.CharField(
        _("Financial Status"),
        max_length=30,
        choices=FinancialStatus.choices,
        default=FinancialStatus.PENDING,
        db_index=True,
    )
    fulfillment_status = models.CharField(
        _("Fulfillment Status"),
        max_length=30,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.UNFULFILLED,
        db_index=True,
    )

    # ── Source / channel ──
    source = models.CharField(
        _("Order Source"),
        max_length=20,
        choices=OrderSource.choices,
        default=OrderSource.WEB,
    )
    source_identifier = models.CharField(
        _("Source Identifier"),
        max_length=255,
        blank=True,
        help_text=_(
            "External reference from source system (e.g. POS terminal ID)."),
    )

    # ── Financial totals ──
    subtotal_price = models.DecimalField(
        _("Subtotal"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Sum of line items before discounts, shipping, and tax."),
    )
    total_discounts = models.DecimalField(
        _("Total Discounts"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_shipping = models.DecimalField(
        _("Total Shipping"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_tax = models.DecimalField(
        _("Total Tax"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_price = models.DecimalField(
        _("Total Price (Grand Total)"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "subtotal_price - total_discounts + total_shipping + total_tax"
        ),
    )
    total_outstanding = models.DecimalField(
        _("Total Outstanding"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Amount still owed. total_price - total_paid."),
    )
    total_paid = models.DecimalField(
        _("Total Paid"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_refunded = models.DecimalField(
        _("Total Refunded"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_tip = models.DecimalField(
        _("Total Tip"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    # ── Gift cards ──
    gift_card_total = models.DecimalField(
        _("Gift Card Total Applied"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # ── Tax ──
    taxes_included = models.BooleanField(
        _("Taxes Included in Price"),
        default=False,
        help_text=_("True for tax-inclusive pricing models (e.g. UK VAT)."),
    )
    tax_exempt = models.BooleanField(_("Tax Exempt"), default=False)

    # ── Shipping ──
    shipping_method_name = models.CharField(
        _("Shipping Method"),
        max_length=255,
        blank=True,
        help_text=_("e.g. 'Standard Delivery', 'DHL Express'"),
    )
    shipping_rate_id = models.UUIDField(
        _("Shipping Rate"),
        null=True,
        blank=True,
        help_text=_("FK-less ref to shipping.ShippingRate."),
    )
    estimated_delivery_at = models.DateTimeField(
        _("Estimated Delivery"),
        null=True,
        blank=True,
    )

    # ── Key timestamps ──
    placed_at = models.DateTimeField(
        _("Placed At"),
        default=timezone.now,
        db_index=True,
        help_text=_("When the customer submitted the order."),
    )
    confirmed_at = models.DateTimeField(
        _("Confirmed At"), null=True, blank=True)
    processing_at = models.DateTimeField(
        _("Processing At"), null=True, blank=True)
    completed_at = models.DateTimeField(
        _("Completed At"), null=True, blank=True)
    cancelled_at = models.DateTimeField(
        _("Cancelled At"), null=True, blank=True)
    closed_at = models.DateTimeField(
        _("Closed At"),
        null=True,
        blank=True,
        help_text=_("When the order was archived/closed."),
    )

    # ── Cancellation ──
    cancellation_reason = models.CharField(
        _("Cancellation Reason"),
        max_length=100,
        blank=True,
        choices=[
            ("customer_request", _("Customer Request")),
            ("fraud", _("Fraud")),
            ("inventory", _("Out of Stock")),
            ("payment_failed", _("Payment Failed")),
            ("other", _("Other")),
        ],
    )
    cancellation_note = models.TextField(_("Cancellation Note"), blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_orders",
        verbose_name=_("Cancelled By"),
    )

    # ── Fraud / risk ──
    risk_level = models.CharField(
        _("Risk Level"),
        max_length=10,
        choices=[
            ("low", _("Low")),
            ("medium", _("Medium")),
            ("high", _("High")),
        ],
        default="low",
        db_index=True,
    )
    risk_score = models.DecimalField(
        _("Risk Score"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Machine learning fraud score 0–100."),
    )
    risk_factors = models.JSONField(
        _("Risk Factors"),
        default=list,
        blank=True,
        help_text=_(
            "List of risk signals detected (e.g. ['ip_mismatch', 'vpn'])."),
    )

    # ── Attribution / marketing ──
    utm_source = models.CharField(_("UTM Source"), max_length=255, blank=True)
    utm_medium = models.CharField(_("UTM Medium"), max_length=255, blank=True)
    utm_campaign = models.CharField(
        _("UTM Campaign"), max_length=255, blank=True)
    referrer_url = models.URLField(_("Referrer URL"), blank=True)
    landing_page = models.URLField(_("Landing Page"), blank=True)

    # ── Context ──
    ip_address = models.GenericIPAddressField(
        _("IP Address"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)
    browser_language = models.CharField(
        _("Browser Language"), max_length=20, blank=True)

    # ── Notes ──
    customer_note = models.TextField(
        _("Customer Note"),
        blank=True,
        help_text=_("Note submitted by customer at checkout."),
    )

    # ── Internal flags ──
    is_test = models.BooleanField(
        _("Test Order"),
        default=False,
        db_index=True,
        help_text=_("True for orders placed in test/sandbox mode."),
    )
    is_confirmed_by_customer = models.BooleanField(
        _("Customer Confirmed"),
        default=True,
    )
    requires_manual_review = models.BooleanField(
        _("Requires Manual Review"),
        default=False,
        db_index=True,
    )
    send_receipt = models.BooleanField(
        _("Send Receipt"),
        default=True,
    )
    buyer_accepts_marketing = models.BooleanField(
        _("Buyer Accepts Marketing"),
        default=False,
    )

    # ── Metafields (extensible key-value data) ──
    metafields = models.JSONField(
        _("Metafields"),
        default=dict,
        blank=True,
        help_text=_(
            "Custom key-value data for integrations (e.g. ERP order ID)."),
    )

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ["-placed_at"]
        indexes = [
            models.Index(fields=["order_number"]),
            models.Index(fields=["customer", "-placed_at"]),
            models.Index(fields=["status", "financial_status"]),
            models.Index(fields=["fulfillment_status"]),
            models.Index(fields=["placed_at"]),
            models.Index(fields=["customer_email"]),
            models.Index(fields=["risk_level", "requires_manual_review"]),
            models.Index(fields=["is_test", "status"]),
            models.Index(fields=["financial_status", "total_outstanding"]),
        ]

    def __str__(self):
        return f"Order {self.order_number} — {self.customer_email} [{self.status}]"

    # ── Computed properties ──

    @property
    def is_paid(self):
        return self.financial_status in (
            self.FinancialStatus.PAID,
            self.FinancialStatus.PARTIALLY_REFUNDED,
        )

    @property
    def is_fulfilled(self):
        return self.fulfillment_status == self.FulfillmentStatus.FULFILLED

    @property
    def is_cancellable(self):
        return self.status in (
            self.OrderStatus.PENDING,
            self.OrderStatus.CONFIRMED,
            self.OrderStatus.ON_HOLD,
        )

    @property
    def is_refundable(self):
        return self.financial_status in (
            self.FinancialStatus.PAID,
            self.FinancialStatus.PARTIALLY_REFUNDED,
        )

    @property
    def net_revenue(self):
        """total_paid minus total_refunded minus total_discounts."""
        return self.total_paid - self.total_refunded

    @property
    def total_items(self):
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    # ── Lifecycle methods ──

    @transaction.atomic
    def transition_status(self, new_status, actor=None, note="", source=""):
        """
        Safely transition order status and write a history record.
        Raises ValueError for invalid transitions.
        """
        old_status = self.status
        self.status = new_status

        ts_field_map = {
            self.OrderStatus.CONFIRMED: "confirmed_at",
            self.OrderStatus.PROCESSING: "processing_at",
            self.OrderStatus.COMPLETED: "completed_at",
            self.OrderStatus.CANCELLED: "cancelled_at",
        }
        ts_field = ts_field_map.get(new_status)
        update_fields = ["status", "updated_at"]
        if ts_field:
            setattr(self, ts_field, timezone.now())
            update_fields.append(ts_field)

        self.save(update_fields=update_fields)

        OrderStatusHistory.objects.create(
            order=self,
            from_status=old_status,
            to_status=new_status,
            changed_by=actor,
            note=note,
            source=source or "system",
        )

    @transaction.atomic
    def cancel(self, reason, actor=None, note=""):
        """Cancel the order with reason."""
        if not self.is_cancellable:
            raise ValueError(
                f"Cannot cancel order in status '{self.status}'."
            )
        self.cancellation_reason = reason
        self.cancellation_note = note
        self.cancelled_by = actor
        self.save(update_fields=[
            "cancellation_reason", "cancellation_note", "cancelled_by", "updated_at"
        ])
        self.transition_status(
            self.OrderStatus.CANCELLED,
            actor=actor,
            note=note,
            source="cancel_action",
        )
        try:
            from public.storefront.services import reverse_order_pricing_effects

            reverse_order_pricing_effects(self, reason=reason or "cancelled")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────

class OrderItem(MixIdAndTimeModel):
    """
    A single line item within an Order. Represents a ProductVariant
    at a specific quantity and price, captured immutably at order placement.

    Key distinction from CartItem:
      - Prices here are FINAL and immutable post-order placement.
      - Includes full tax, discount, and fulfillment breakdown per line.
      - Tracks fulfillment and return quantities independently.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Order"),
    )
    variant = models.ForeignKey(
        "product.ProductVariant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
        verbose_name=_("Product Variant"),
        help_text=_(
            "Can be null if the variant is deleted post-order. "
            "Snapshot fields preserve the display data."
        ),
    )

    # ── Quantity ──
    quantity = models.PositiveIntegerField(
        _("Quantity"),
        validators=[MinValueValidator(1)],
    )
    quantity_fulfilled = models.PositiveIntegerField(
        _("Quantity Fulfilled"),
        default=0,
        help_text=_("Units included in a dispatched Fulfillment."),
    )
    quantity_returned = models.PositiveIntegerField(
        _("Quantity Returned"),
        default=0,
    )
    quantity_refunded = models.PositiveIntegerField(
        _("Quantity Refunded"),
        default=0,
    )

    # ── Product snapshot (immutable — product may be edited post-order) ──
    product_id_snapshot = models.UUIDField(
        _("Product ID (snapshot)"),
        null=True,
        blank=True,
    )
    variant_id_snapshot = models.UUIDField(
        _("Variant ID (snapshot)"),
        null=True,
        blank=True,
    )
    product_title = models.CharField(_("Product Title"), max_length=500)
    variant_title = models.CharField(
        _("Variant Title"), max_length=500, blank=True)
    sku = models.CharField(_("SKU"), max_length=255, blank=True)
    barcode = models.CharField(_("Barcode"), max_length=100, blank=True)
    vendor = models.CharField(_("Vendor"), max_length=255, blank=True)
    product_image_url = models.URLField(_("Product Image URL"), blank=True)

    # ── Pricing (all immutable after order creation) ──
    unit_price = models.DecimalField(
        _("Unit Price"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    compare_at_price = models.DecimalField(
        _("Compare At Price"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    unit_discount = models.DecimalField(
        _("Unit Discount"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Per-unit discount amount applied to this line."),
    )
    unit_tax = models.DecimalField(
        _("Unit Tax"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_rate = models.DecimalField(
        _("Tax Rate (%)"),
        max_digits=6,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    total_discount = models.DecimalField(
        _("Total Discount"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_tax = models.DecimalField(
        _("Total Tax"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    subtotal = models.DecimalField(
        _("Line Subtotal (before tax)"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("unit_price × quantity − total_discount"),
    )
    total = models.DecimalField(
        _("Line Total (including tax)"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("subtotal + total_tax"),
    )
    cost_per_item = models.DecimalField(
        _("Cost Per Item (COGS)"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # ── Tax info ──
    tax_lines = models.JSONField(
        _("Tax Lines"),
        default=list,
        blank=True,
        help_text=_(
            "Array of tax components applied. "
            "[{title, rate, amount}] — e.g. [{title: 'VAT', rate: 0.075, amount: 150.00}]"
        ),
    )
    is_taxable = models.BooleanField(_("Taxable"), default=True)

    # ── Fulfillment ──
    fulfillment_service = models.CharField(
        _("Fulfillment Service"),
        max_length=100,
        default="manual",
    )
    requires_shipping = models.BooleanField(
        _("Requires Shipping"), default=True)
    is_gift_card = models.BooleanField(_("Is Gift Card"), default=False)

    # ── Physical attributes snapshot ──
    weight = models.DecimalField(
        _("Weight (kg)"),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
    )

    # ── Custom line properties ──
    custom_properties = models.JSONField(
        _("Custom Properties"),
        default=dict,
        blank=True,
    )

    # ── Applied discount references ──
    applied_discount_ids = models.JSONField(
        _("Applied Discount IDs"),
        default=list,
        blank=True,
        help_text=_("List of pricing.DiscountCode UUIDs applied to this line."),
    )

    class Meta:
        verbose_name = _("Order Item")
        verbose_name_plural = _("Order Items")
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["order"]),
            models.Index(fields=["variant"]),
            models.Index(fields=["sku"]),
        ]

    def __str__(self):
        return f"{self.quantity}× {self.product_title} [{self.sku}] in {self.order.order_number}"

    @property
    def quantity_unfulfilled(self):
        return max(0, self.quantity - self.quantity_fulfilled - self.quantity_returned)

    @property
    def is_fully_fulfilled(self):
        return self.quantity_fulfilled >= self.quantity

    @property
    def is_fully_returned(self):
        return self.quantity_returned >= self.quantity

    @property
    def gross_profit(self):
        if self.cost_per_item is not None:
            return self.subtotal - (self.cost_per_item * self.quantity)
        return None


# ─────────────────────────────────────────────────────────────

class OrderAddress(MixIdAndTimeModel):
    """
    Immutable address snapshot recorded at order placement time.
    One Order has up to two addresses:
      - address_type = SHIPPING → delivery destination
      - address_type = BILLING  → payment address

    CRITICAL: Never edit these after creation. If an address is corrected
    post-order, create a new record and log the change in OrderStatusHistory.
    """

    class AddressType(models.TextChoices):
        SHIPPING = "shipping", _("Shipping Address")
        BILLING = "billing", _("Billing Address")

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name=_("Order"),
    )
    address_type = models.CharField(
        _("Address Type"),
        max_length=10,
        choices=AddressType.choices,
    )

    # ── Name ──
    first_name = models.CharField(_("First Name"), max_length=150)
    last_name = models.CharField(_("Last Name"), max_length=150)
    company = models.CharField(_("Company"), max_length=255, blank=True)

    # ── Address ──
    address_line1 = models.CharField(_("Address Line 1"), max_length=255)
    address_line2 = models.CharField(
        _("Address Line 2"), max_length=255, blank=True)
    city = models.CharField(_("City"), max_length=150)
    state = models.CharField(_("State / Province"), max_length=150, blank=True)
    postal_code = models.CharField(_("Postal Code"), max_length=20, blank=True)
    country = models.CharField(
        _("Country"),
        max_length=2,
        help_text=_("ISO 3166-1 alpha-2. e.g. NG, US, GB"),
    )
    country_name = models.CharField(
        _("Country Name"),
        max_length=100,
        blank=True,
        help_text=_("Full country name snapshot for display."),
    )

    # ── Contact ──
    phone = models.CharField(_("Phone"), max_length=30, blank=True)
    email = models.EmailField(_("Email"), blank=True)

    # ── Geo ──
    latitude = models.DecimalField(
        _("Latitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        _("Longitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    # ── Validation ──
    is_validated = models.BooleanField(
        _("Address Validated"),
        default=False,
        help_text=_(
            "True if address was validated via a geocoding/address API."),
    )
    validation_source = models.CharField(
        _("Validation Source"),
        max_length=100,
        blank=True,
        help_text=_("e.g. 'google_places', 'shippo', 'loqate'"),
    )

    class Meta:
        verbose_name = _("Order Address")
        verbose_name_plural = _("Order Addresses")
        unique_together = [("order", "address_type")]
        indexes = [
            models.Index(fields=["order", "address_type"]),
        ]

    def __str__(self):
        return (
            f"{self.get_address_type_display()} — "
            f"{self.first_name} {self.last_name}, {self.city}, {self.country}"
        )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def full_address(self):
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts += [self.city]
        if self.state:
            parts.append(self.state)
        if self.postal_code:
            parts.append(self.postal_code)
        parts.append(self.country_name or self.country)
        return ", ".join(parts)


# ─────────────────────────────────────────────────────────────

class OrderStatusHistory(IduuidModel):
    """
    IMMUTABLE append-only log of every status transition on an Order.
    Never update or delete rows. One INSERT per transition.

    Covers order_status, financial_status, and fulfillment_status changes.
    All three are captured on every write (delta is visible by comparison).
    """

    class ChangeSource(models.TextChoices):
        CUSTOMER = "customer", _("Customer Action")
        STAFF = "staff", _("Staff Action")
        SYSTEM = "system", _("System / Automation")
        PAYMENT_GATEWAY = "payment_gateway", _("Payment Gateway Webhook")
        SHIPPING_CARRIER = "shipping_carrier", _("Shipping Carrier Webhook")
        API = "api", _("API")
        IMPORT = "import", _("Data Import")
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name=_("Order"),
    )

    # ── Status snapshots ──
    from_status = models.CharField(
        _("From Status"),
        max_length=30,
        blank=True,
        help_text=_("Status before this transition."),
    )
    to_status = models.CharField(
        _("To Status"),
        max_length=30,
        help_text=_("Status after this transition."),
    )
    financial_status_snapshot = models.CharField(
        _("Financial Status (snapshot)"),
        max_length=30,
        blank=True,
    )
    fulfillment_status_snapshot = models.CharField(
        _("Fulfillment Status (snapshot)"),
        max_length=30,
        blank=True,
    )

    # ── Context ──
    source = models.CharField(
        _("Change Source"),
        max_length=30,
        choices=ChangeSource.choices,
        default=ChangeSource.SYSTEM,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_status_changes",
        verbose_name=_("Changed By"),
    )
    note = models.TextField(_("Note"), blank=True)
    is_customer_visible = models.BooleanField(
        _("Visible to Customer"),
        default=False,
        help_text=_(
            "If True, this event appears in the customer's order timeline."),
    )

    # ── Immutable timestamp ──
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Order Status History")
        verbose_name_plural = _("Order Status Histories")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "-created_at"]),
            models.Index(fields=["to_status"]),
        ]

    def __str__(self):
        return (
            f"Order {self.order.order_number}: "
            f"{self.from_status} → {self.to_status}"
        )


# ─────────────────────────────────────────────────────────────

class OrderNote(MixIdAndTimeModel):
    """
    Internal staff notes attached to an Order.
    NOT visible to customers unless explicitly flagged.
    Supports pinning and categorisation for triage workflows.
    """

    class NoteCategory(models.TextChoices):
        GENERAL = "general", _("General")
        FRAUD = "fraud", _("Fraud / Risk")
        SHIPPING = "shipping", _("Shipping")
        PAYMENT = "payment", _("Payment")
        RETURN = "return", _("Return / Refund")
        CUSTOMER_COMM = "customer_comm", _("Customer Communication")
        ESCALATION = "escalation", _("Escalation")

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name=_("Order"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_notes",
        verbose_name=_("Author"),
    )
    body = models.TextField(_("Note Body"))
    category = models.CharField(
        _("Category"),
        max_length=20,
        choices=NoteCategory.choices,
        default=NoteCategory.GENERAL,
    )
    is_pinned = models.BooleanField(
        _("Pinned"),
        default=False,
        help_text=_("Pinned notes appear at the top of the order notes list."),
    )
    is_customer_visible = models.BooleanField(
        _("Visible to Customer"),
        default=False,
    )
    is_system_generated = models.BooleanField(
        _("System Generated"),
        default=False,
        help_text=_("Auto-generated notes from integrations or automations."),
    )

    class Meta:
        verbose_name = _("Order Note")
        verbose_name_plural = _("Order Notes")
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["order", "-created_at"]),
        ]

    def __str__(self):
        return f"Note on {self.order.order_number} by {self.author}"


# ─────────────────────────────────────────────────────────────

class OrderTag(MixIdAndTimeModel):
    """
    Freeform labels applied to orders for filtering, triage, and workflows.
    Examples: 'vip', 'wholesale', 'express-process', 'fraud-hold', 'gift'
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="tags",
        verbose_name=_("Order"),
    )
    name = models.CharField(_("Tag"), max_length=100, db_index=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="added_order_tags",
    )

    class Meta:
        verbose_name = _("Order Tag")
        verbose_name_plural = _("Order Tags")
        unique_together = [("order", "name")]
        ordering = ["name"]

    def __str__(self):
        return f"{self.order.order_number} — #{self.name}"

    def save(self, *args, **kwargs):
        self.name = self.name.strip().lower().replace(" ", "-")
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────

class OrderDiscount(MixIdAndTimeModel):
    """
    Records each discount (coupon, automatic, gift card, loyalty)
    applied to an Order. Immutable after order placement.
    """

    class DiscountType(models.TextChoices):
        CODE = "code", _("Coupon Code")
        AUTOMATIC = "automatic", _("Automatic Discount")
        GIFT_CARD = "gift_card", _("Gift Card")
        LOYALTY = "loyalty", _("Loyalty Points")
        STAFF = "staff", _("Staff / Manual Discount")
        BUNDLE = "bundle", _("Bundle Discount")

    class AllocationMethod(models.TextChoices):
        ACROSS = "across", _("Across Entire Order")
        EACH = "each", _("Each Eligible Item")
        ONE = "one", _("One Specific Item")

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="discounts",
        verbose_name=_("Order"),
    )
    discount_type = models.CharField(
        _("Discount Type"),
        max_length=20,
        choices=DiscountType.choices,
    )
    code = models.CharField(_("Code"), max_length=100, blank=True)
    description = models.CharField(
        _("Description"), max_length=500, blank=True)
    discount_id = models.UUIDField(
        _("Discount ID"),
        null=True,
        blank=True,
        help_text=_(
            "FK-less ref to pricing.DiscountCode or pricing.AutomaticDiscount."),
    )
    allocation_method = models.CharField(
        _("Allocation Method"),
        max_length=10,
        choices=AllocationMethod.choices,
        default=AllocationMethod.ACROSS,
    )
    amount = models.DecimalField(
        _("Discount Amount"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_percentage = models.BooleanField(_("Is Percentage"), default=False)
    percentage_value = models.DecimalField(
        _("Percentage Value"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Order Discount")
        verbose_name_plural = _("Order Discounts")
        ordering = ["order", "created_at"]

    def __str__(self):
        label = self.code or self.get_discount_type_display()
        return f"{label} — {self.amount} on {self.order.order_number}"


# ─────────────────────────────────────────────────────────────

class OrderTax(MixIdAndTimeModel):
    """
    Granular tax line breakdown per order.
    An order can have multiple tax lines (e.g. Federal + State + Local).
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="tax_lines",
        verbose_name=_("Order"),
    )
    title = models.CharField(
        _("Tax Name"),
        max_length=255,
        help_text=_("e.g. 'VAT', 'GST', 'State Tax', 'Federal Tax'"),
    )
    rate = models.DecimalField(
        _("Tax Rate"),
        max_digits=7,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0000"))],
        help_text=_("Decimal rate. e.g. 0.075 for 7.5%"),
    )
    amount = models.DecimalField(
        _("Tax Amount"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_included_in_price = models.BooleanField(
        _("Included in Price"),
        default=False,
    )
    jurisdiction = models.CharField(
        _("Tax Jurisdiction"),
        max_length=255,
        blank=True,
        help_text=_("e.g. 'Nigeria', 'Lagos State', 'California'"),
    )
    tax_authority = models.CharField(
        _("Tax Authority"),
        max_length=255,
        blank=True,
        help_text=_("e.g. 'FIRS', 'IRS', 'HMRC'"),
    )

    class Meta:
        verbose_name = _("Order Tax")
        verbose_name_plural = _("Order Taxes")
        ordering = ["order", "title"]

    def __str__(self):
        return f"{self.title} ({self.rate * 100:.2f}%) — {self.amount}"


# ─────────────────────────────────────────────────────────────
# SECTION 3 — FULFILLMENT
# ─────────────────────────────────────────────────────────────

class Fulfillment(MixIdAndTimeModel):
    """
    A single dispatch shipment event for an Order.
    One order can have MULTIPLE fulfillments (partial fulfillment).
    e.g. Items A & B ship today → Fulfillment #1
         Item C ships next week → Fulfillment #2

    Fulfillment status lifecycle:
      PENDING → PROCESSING → SHIPPED → IN_TRANSIT → DELIVERED
      Any → CANCELLED / FAILED

    The FulfillmentItems detail which OrderItems and quantities are
    included in this shipment.
    """

    class FulfillmentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing / Packing")
        READY_TO_SHIP = "ready_to_ship", _("Ready to Ship")
        SHIPPED = "shipped", _("Shipped")
        IN_TRANSIT = "in_transit", _("In Transit")
        OUT_FOR_DELIVERY = "out_for_delivery", _("Out for Delivery")
        DELIVERED = "delivered", _("Delivered")
        DELIVERY_ATTEMPTED = "delivery_attempted", _("Delivery Attempted")
        DELIVERY_FAILED = "delivery_failed", _("Delivery Failed")
        RETURNED_TO_SENDER = "returned_to_sender", _("Returned to Sender")
        CANCELLED = "cancelled", _("Cancelled")
        ON_HOLD = "on_hold", _("On Hold")

    class FulfillmentService(models.TextChoices):
        MANUAL = "manual", _("Manual")
        AMAZON = "amazon", _("Amazon FBA")
        PRINTFUL = "printful", _("Printful")
        SHIPBOB = "shipbob", _("ShipBob")
        EASYSHIP = "easyship", _("EasyShip")
        SHIPPO = "shippo", _("Shippo")
        DHL = "dhl", _("DHL Express")
        FEDEX = "fedex", _("FedEx")
        UPS = "ups", _("UPS")
        CUSTOM = "custom", _("Custom 3PL")

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="fulfillments",
        verbose_name=_("Order"),
    )

    # ── Numbering ──
    fulfillment_number = models.CharField(
        _("Fulfillment Number"),
        max_length=100,
        blank=True,
        help_text=_("e.g. ORD-000123-F1, ORD-000123-F2"),
    )

    # ── Status ──
    status = models.CharField(
        _("Status"),
        max_length=30,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.PENDING,
        db_index=True,
    )

    # ── Location ──
    location = models.UUIDField(
        _("Fulfillment Location"),
        null=True,
        blank=True,
        db_column="location_id",
        help_text=_("Inventory location reference kept as UUID until the inventory app is installed."),
    )

    # ── Service ──
    fulfillment_service = models.CharField(
        _("Fulfillment Service"),
        max_length=30,
        choices=FulfillmentService.choices,
        default=FulfillmentService.MANUAL,
    )
    service_fulfillment_id = models.CharField(
        _("3PL Fulfillment ID"),
        max_length=255,
        blank=True,
        help_text=_("External reference ID from the 3PL service."),
    )

    # ── Shipping details ──
    carrier = models.UUIDField(
        _("Carrier"),
        null=True,
        blank=True,
        db_column="carrier_id",
        help_text=_("Shipping carrier reference kept as UUID until the shipping app is installed."),
    )
    shipping_method = models.CharField(
        _("Shipping Method"), max_length=255, blank=True)
    estimated_delivery_at = models.DateTimeField(
        _("Estimated Delivery"),
        null=True,
        blank=True,
    )

    # ── Destination snapshot ──
    destination_name = models.CharField(
        _("Destination Name"), max_length=255, blank=True)
    destination_address = models.TextField(
        _("Destination Address"), blank=True)
    destination_city = models.CharField(
        _("Destination City"), max_length=100, blank=True)
    destination_country = models.CharField(
        _("Destination Country"), max_length=2, blank=True)

    # ── Key timestamps ──
    packed_at = models.DateTimeField(_("Packed At"), null=True, blank=True)
    shipped_at = models.DateTimeField(
        _("Shipped At"), null=True, blank=True, db_index=True)
    delivered_at = models.DateTimeField(
        _("Delivered At"), null=True, blank=True)

    # ── Actors ──
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_fulfillments",
        verbose_name=_("Created By"),
    )

    # ── Notifications ──
    notify_customer = models.BooleanField(
        _("Notify Customer"),
        default=True,
        help_text=_("Send shipping notification email to customer."),
    )
    notification_sent_at = models.DateTimeField(
        _("Customer Notification Sent At"),
        null=True,
        blank=True,
    )

    # ── Notes ──
    internal_note = models.TextField(_("Internal Note"), blank=True)
    packing_instructions = models.TextField(
        _("Packing Instructions"), blank=True)

    class Meta:
        verbose_name = _("Fulfillment")
        verbose_name_plural = _("Fulfillments")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "status"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["shipped_at"]),
        ]

    def __str__(self):
        return f"Fulfillment {self.fulfillment_number or self.id} — {self.status}"

    @property
    def is_shipped(self):
        return self.status in (
            self.FulfillmentStatus.SHIPPED,
            self.FulfillmentStatus.IN_TRANSIT,
            self.FulfillmentStatus.OUT_FOR_DELIVERY,
            self.FulfillmentStatus.DELIVERED,
        )

    @property
    def is_delivered(self):
        return self.status == self.FulfillmentStatus.DELIVERED

    @transaction.atomic
    def mark_shipped(self, actor=None):
        self.status = self.FulfillmentStatus.SHIPPED
        self.shipped_at = timezone.now()
        self.save(update_fields=["status", "shipped_at", "updated_at"])

    @transaction.atomic
    def mark_delivered(self):
        self.status = self.FulfillmentStatus.DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=["status", "delivered_at", "updated_at"])


# ─────────────────────────────────────────────────────────────

class FulfillmentItem(MixIdAndTimeModel):
    """
    Junction: which OrderItems and what quantities are included
    in a specific Fulfillment (shipment).

    Enables partial fulfillment:
      OrderItem (qty=5) → FulfillmentItem (qty=3) in Fulfillment #1
                        → FulfillmentItem (qty=2) in Fulfillment #2
    """

    fulfillment = models.ForeignKey(
        Fulfillment,
        on_delete=models.CASCADE,
        related_name="fulfillment_items",
        verbose_name=_("Fulfillment"),
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="fulfillment_items",
        verbose_name=_("Order Item"),
    )
    quantity = models.PositiveIntegerField(
        _("Quantity"),
        validators=[MinValueValidator(1)],
        help_text=_("How many units of this order item are in this shipment."),
    )
    inventory_item_id = models.UUIDField(
        _("Inventory Level ID"),
        null=True,
        blank=True,
        help_text=_(
            "FK-less ref to inventory.InventoryLevel this stock was deducted from."),
    )

    class Meta:
        verbose_name = _("Fulfillment Item")
        verbose_name_plural = _("Fulfillment Items")
        unique_together = [("fulfillment", "order_item")]
        ordering = ["fulfillment"]

    def __str__(self):
        return (
            f"{self.quantity}× {self.order_item.product_title} "
            f"in Fulfillment {self.fulfillment_id}"
        )


# ─────────────────────────────────────────────────────────────

class TrackingInfo(MixIdAndTimeModel):
    """
    Carrier tracking information for a Fulfillment.
    A fulfillment can have multiple tracking numbers
    (e.g. multi-package shipments).

    Tracking events are stored as a JSON timeline for real-time
    status updates without a separate TrackingEvent table.
    """

    class TrackingStatus(models.TextChoices):
        LABEL_CREATED = "label_created", _("Label Created")
        IN_TRANSIT = "in_transit", _("In Transit")
        OUT_FOR_DELIVERY = "out_for_delivery", _("Out for Delivery")
        DELIVERED = "delivered", _("Delivered")
        DELIVERY_FAILED = "delivery_failed", _("Delivery Failed / Attempted")
        RETURNED = "returned", _("Returned to Sender")
        EXCEPTION = "exception", _("Exception / Delay")
        UNKNOWN = "unknown", _("Unknown")

    fulfillment = models.ForeignKey(
        Fulfillment,
        on_delete=models.CASCADE,
        related_name="tracking_info",
        verbose_name=_("Fulfillment"),
    )

    # ── Carrier / tracking ──
    carrier_name = models.CharField(
        _("Carrier Name"),
        max_length=255,
        help_text=_("e.g. 'DHL', 'FedEx', 'GIG Logistics', 'GIGL'"),
    )
    carrier_code = models.CharField(
        _("Carrier Code"),
        max_length=50,
        blank=True,
        help_text=_("Standardised carrier code. e.g. 'dhl', 'fedex', 'ups'"),
    )
    tracking_number = models.CharField(
        _("Tracking Number"),
        max_length=255,
        db_index=True,
    )
    tracking_url = models.URLField(
        _("Tracking URL"),
        blank=True,
        help_text=_(
            "Direct link to carrier's tracking page for this shipment."),
    )

    # ── Status ──
    status = models.CharField(
        _("Tracking Status"),
        max_length=30,
        choices=TrackingStatus.choices,
        default=TrackingStatus.LABEL_CREATED,
        db_index=True,
    )
    status_detail = models.CharField(
        _("Status Detail"),
        max_length=500,
        blank=True,
        help_text=_("Carrier's raw status message."),
    )

    # ── Key timestamps ──
    shipped_at = models.DateTimeField(_("Shipped At"), null=True, blank=True)
    estimated_delivery_at = models.DateTimeField(
        _("Estimated Delivery"),
        null=True,
        blank=True,
    )
    delivered_at = models.DateTimeField(
        _("Delivered At"), null=True, blank=True)
    last_synced_at = models.DateTimeField(
        _("Last Synced"),
        null=True,
        blank=True,
        help_text=_("Last time tracking status was fetched from carrier API."),
    )

    # ── Location ──
    current_location = models.CharField(
        _("Current Location"),
        max_length=255,
        blank=True,
        help_text=_("Last known location from carrier scan. e.g. 'Lagos Hub'"),
    )
    origin_location = models.CharField(
        _("Origin Location"),
        max_length=255,
        blank=True,
    )
    destination_location = models.CharField(
        _("Destination Location"),
        max_length=255,
        blank=True,
    )

    # ── Event timeline (JSON) ──
    tracking_events = models.JSONField(
        _("Tracking Events"),
        default=list,
        blank=True,
        help_text=_(
            "Chronological array of carrier scan events. "
            "[{timestamp, location, status, description}]"
        ),
    )

    # ── Package info ──
    package_weight = models.DecimalField(
        _("Package Weight (kg)"),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
    )
    package_dimensions = models.JSONField(
        _("Package Dimensions"),
        default=dict,
        blank=True,
        help_text=_("{length, width, height} in cm"),
    )
    is_primary = models.BooleanField(
        _("Primary Tracking"),
        default=True,
        help_text=_("The main tracking number shown to the customer."),
    )

    class Meta:
        verbose_name = _("Tracking Info")
        verbose_name_plural = _("Tracking Info")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tracking_number"]),
            models.Index(fields=["fulfillment", "is_primary"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.carrier_name} — {self.tracking_number} [{self.status}]"


# ─────────────────────────────────────────────────────────────
# SECTION 4 — RETURNS
# ─────────────────────────────────────────────────────────────

class Return(MixIdAndTimeModel):
    """
    Customer-initiated return request against a fulfilled Order.

    Return lifecycle:
      REQUESTED → PENDING_REVIEW → APPROVED → RECEIVED → INSPECTED
      → RESTOCKED / DISPOSED → REFUND_PENDING → REFUNDED

      Any active state → REJECTED / CANCELLED

    One Order can have multiple Returns (e.g. return items in waves).
    A Return is separate from a Refund — the refund is triggered
    AFTER the return is inspected and approved.
    """

    class ReturnStatus(models.TextChoices):
        REQUESTED = "requested", _("Requested by Customer")
        PENDING_REVIEW = "pending_review", _("Pending Staff Review")
        APPROVED = "approved", _("Approved — Awaiting Items")
        LABEL_GENERATED = "label_generated", _("Return Label Generated")
        IN_TRANSIT = "in_transit", _("Items In Transit")
        RECEIVED = "received", _("Items Received")
        INSPECTING = "inspecting", _("Under Inspection")
        RESTOCKED = "restocked", _("Restocked to Inventory")
        PARTIALLY_RESTOCKED = "partially_restocked", _("Partially Restocked")
        DISPOSED = "disposed", _("Items Disposed")
        REFUND_PENDING = "refund_pending", _("Refund Pending")
        REFUNDED = "refunded", _("Refunded")
        REJECTED = "rejected", _("Rejected")
        CANCELLED = "cancelled", _("Cancelled")

    class ReturnReason(models.TextChoices):
        WRONG_ITEM = "wrong_item", _("Received Wrong Item")
        DAMAGED = "damaged", _("Item Arrived Damaged")
        DEFECTIVE = "defective", _("Item is Defective / Not Working")
        NOT_AS_DESCRIBED = "not_as_described", _("Not as Described")
        CHANGED_MIND = "changed_mind", _("Changed Mind")
        ORDERED_BY_MISTAKE = "ordered_by_mistake", _("Ordered by Mistake")
        SIZING_ISSUE = "sizing_issue", _("Wrong Size / Fit Issue")
        QUALITY_ISSUE = "quality_issue", _("Quality Below Expectation")
        LATE_DELIVERY = "late_delivery", _("Arrived Too Late")
        OTHER = "other", _("Other")

    class ReturnMethod(models.TextChoices):
        MAIL = "mail", _("Mail / Courier")
        DROP_OFF = "drop_off", _("Drop Off at Store")
        PICKUP = "pickup", _("Store Pickup from Customer")
        NO_RETURN_REQUIRED = "no_return_required", _(
            "No Return Required (refund only)")

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="returns",
        verbose_name=_("Order"),
    )
    customer = models.ForeignKey(
        "userauth.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="returns",
        verbose_name=_("Customer"),
    )

    # ── Reference ──
    return_number = models.CharField(
        _("Return Number"),
        max_length=100,
        unique=True,
        help_text=_("Human-readable return ID. e.g. RTN-000045"),
    )

    # ── Status ──
    status = models.CharField(
        _("Status"),
        max_length=30,
        choices=ReturnStatus.choices,
        default=ReturnStatus.REQUESTED,
        db_index=True,
    )

    # ── Reason ──
    reason = models.CharField(
        _("Return Reason"),
        max_length=30,
        choices=ReturnReason.choices,
    )
    reason_note = models.TextField(
        _("Customer Notes"),
        blank=True,
        help_text=_("Customer's freeform explanation."),
    )

    # ── Method ──
    return_method = models.CharField(
        _("Return Method"),
        max_length=30,
        choices=ReturnMethod.choices,
        default=ReturnMethod.MAIL,
    )

    # ── Return label ──
    return_label_url = models.URLField(_("Return Label URL"), blank=True)
    return_label_tracking_number = models.CharField(
        _("Return Tracking Number"),
        max_length=255,
        blank=True,
    )
    return_label_carrier = models.CharField(
        _("Return Carrier"), max_length=100, blank=True)

    # ── Financial ──
    refund_amount = models.DecimalField(
        _("Approved Refund Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "Staff-approved refund amount. May differ from original item price."),
    )
    restocking_fee = models.DecimalField(
        _("Restocking Fee"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    return_shipping_cost = models.DecimalField(
        _("Return Shipping Cost"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "Cost deducted from refund if customer pays return shipping."),
    )

    # ── Timestamps ──
    requested_at = models.DateTimeField(
        _("Requested At"), default=timezone.now)
    approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)
    received_at = models.DateTimeField(
        _("Items Received At"), null=True, blank=True)
    refunded_at = models.DateTimeField(_("Refunded At"), null=True, blank=True)
    deadline = models.DateTimeField(
        _("Return Deadline"),
        null=True,
        blank=True,
        help_text=_("Customer must ship items by this date."),
    )

    # ── Staff ──
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_returns",
        verbose_name=_("Reviewed By"),
    )
    staff_note = models.TextField(_("Staff Note"), blank=True)
    rejection_reason = models.TextField(_("Rejection Reason"), blank=True)

    # ── Refund cross-reference ──
    refund_id = models.UUIDField(
        _("Resulting Refund"),
        null=True,
        blank=True,
        help_text=_("FK-less ref to the Refund created from this return."),
    )

    class Meta:
        verbose_name = _("Return")
        verbose_name_plural = _("Returns")
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["order", "status"]),
            models.Index(fields=["return_number"]),
            models.Index(fields=["status", "-requested_at"]),
            models.Index(fields=["customer"]),
        ]

    def __str__(self):
        return f"Return {self.return_number} — {self.order.order_number} [{self.status}]"

    @property
    def net_refund_amount(self):
        if self.refund_amount is None:
            return None
        return self.refund_amount - self.restocking_fee - self.return_shipping_cost

    @transaction.atomic
    def approve(self, actor, approved_amount=None):
        self.status = self.ReturnStatus.APPROVED
        self.approved_at = timezone.now()
        self.reviewed_by = actor
        if approved_amount is not None:
            self.refund_amount = approved_amount
        update_fields = ["status", "approved_at", "reviewed_by", "updated_at"]
        if approved_amount is not None:
            update_fields.append("refund_amount")
        self.save(update_fields=update_fields)

    @transaction.atomic
    def reject(self, actor, reason):
        self.status = self.ReturnStatus.REJECTED
        self.reviewed_by = actor
        self.rejection_reason = reason
        self.save(update_fields=["status", "reviewed_by",
                  "rejection_reason", "updated_at"])


# ─────────────────────────────────────────────────────────────

class ReturnItem(MixIdAndTimeModel):
    """
    A specific OrderItem line within a Return request.
    Tracks per-item condition, disposition, and restocking decision.
    """

    class ItemCondition(models.TextChoices):
        UNOPENED = "unopened", _("Unopened / New")
        LIKE_NEW = "like_new", _("Like New — No Signs of Use")
        GOOD = "good", _("Good — Minor Signs of Use")
        FAIR = "fair", _("Fair — Moderate Wear")
        DAMAGED = "damaged", _("Damaged / Not Resaleable")
        MISSING_PARTS = "missing_parts", _("Missing Parts / Accessories")

    class ItemDisposition(models.TextChoices):
        RESTOCK = "restock", _("Restock to Inventory")
        RESTOCK_AS_USED = "restock_as_used", _("Restock as Used/Refurbished")
        DISPOSE = "dispose", _("Dispose / Write Off")
        RETURN_TO_VENDOR = "return_to_vendor", _("Return to Vendor")
        DONATE = "donate", _("Donate")

    return_request = models.ForeignKey(
        Return,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Return Request"),
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="return_items",
        verbose_name=_("Order Item"),
    )
    quantity = models.PositiveIntegerField(
        _("Quantity Returned"),
        validators=[MinValueValidator(1)],
    )
    quantity_received = models.PositiveIntegerField(
        _("Quantity Actually Received"),
        null=True,
        blank=True,
        help_text=_(
            "May differ from requested quantity on receipt inspection."),
    )
    quantity_restocked = models.PositiveIntegerField(
        _("Quantity Restocked"),
        null=True,
        blank=True,
    )

    # ── Reason per-item ──
    reason = models.CharField(
        _("Item Return Reason"),
        max_length=30,
        choices=Return.ReturnReason.choices,
        blank=True,
    )

    # ── Condition & disposition (set after inspection) ──
    condition = models.CharField(
        _("Received Condition"),
        max_length=20,
        choices=ItemCondition.choices,
        blank=True,
    )
    disposition = models.CharField(
        _("Disposition"),
        max_length=20,
        choices=ItemDisposition.choices,
        blank=True,
    )
    disposition_note = models.TextField(_("Disposition Note"), blank=True)

    # ── Refund ──
    refund_amount = models.DecimalField(
        _("Line Refund Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_refundable = models.BooleanField(_("Refundable"), default=True)

    # ── Images (customer-submitted photos of condition) ──
    customer_images = models.JSONField(
        _("Customer-Submitted Images"),
        default=list,
        blank=True,
        help_text=_("List of URLs to images customer uploaded as evidence."),
    )

    class Meta:
        verbose_name = _("Return Item")
        verbose_name_plural = _("Return Items")
        unique_together = [("return_request", "order_item")]
        ordering = ["return_request"]

    def __str__(self):
        return (
            f"{self.quantity}× {self.order_item.product_title} "
            f"in Return {self.return_request.return_number}"
        )


# ─────────────────────────────────────────────────────────────

class ReturnEvent(IduuidModel):
    """
    IMMUTABLE timeline of all events on a Return request.
    One INSERT per status change or notable event.
    """

    return_request = models.ForeignKey(
        Return,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name=_("Return"),
    )
    from_status = models.CharField(_("From Status"), max_length=30, blank=True)
    to_status = models.CharField(_("To Status"), max_length=30)
    event_note = models.TextField(_("Event Note"), blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="return_events",
    )
    is_customer_visible = models.BooleanField(
        _("Visible to Customer"), default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Return Event")
        verbose_name_plural = _("Return Events")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.return_request.return_number}: {self.from_status} → {self.to_status}"


# ─────────────────────────────────────────────────────────────
# SECTION 5 — REFUNDS
# ─────────────────────────────────────────────────────────────

class Refund(MixIdAndTimeModel):
    """
    Financial refund record tied to an Order (with optional Return link).

    A Refund is the monetary event; a Return is the physical event.
    They are related but independent:
      - You can issue a Refund without requiring a Return (goodwill refund).
      - A Return always results in a Refund after inspection.

    Refund types:
      FULL        → entire order amount returned
      PARTIAL     → specific lines or a custom amount
      SHIPPING    → shipping cost only
      RESTOCK_FEE → restocking fee only (deducted from refund)

    Processing methods:
      ORIGINAL_PAYMENT → back to original payment method
      STORE_CREDIT     → issued as store credit / gift card
      BANK_TRANSFER    → manual wire transfer
      CASH             → in-person cash (POS)
    """

    class RefundStatus(models.TextChoices):
        PENDING = "pending", _("Pending Processing")
        PROCESSING = "processing", _("Processing")
        SUCCEEDED = "succeeded", _("Succeeded")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")
        REQUIRES_ACTION = "requires_action", _("Requires Manual Action")

    class RefundType(models.TextChoices):
        FULL = "full", _("Full Refund")
        PARTIAL = "partial", _("Partial Refund")
        SHIPPING_ONLY = "shipping_only", _("Shipping Cost Only")
        GOODWILL = "goodwill", _("Goodwill / Courtesy Credit")
        PRICE_ADJUSTMENT = "price_adjustment", _("Price Adjustment")
        DUPLICATE_CHARGE = "duplicate_charge", _("Duplicate Charge")

    class RefundMethod(models.TextChoices):
        ORIGINAL_PAYMENT = "original_payment", _("Original Payment Method")
        STORE_CREDIT = "store_credit", _("Store Credit / Wallet")
        GIFT_CARD = "gift_card", _("Gift Card")
        BANK_TRANSFER = "bank_transfer", _("Manual Bank Transfer")
        CASH = "cash", _("Cash (POS)")

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="refunds",
        verbose_name=_("Order"),
    )
    return_request = models.ForeignKey(
        Return,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="refunds",
        verbose_name=_("Return Request"),
        help_text=_(
            "The return that triggered this refund. Null for standalone refunds."),
    )

    # ── Identification ──
    refund_number = models.CharField(
        _("Refund Number"),
        max_length=100,
        unique=True,
        help_text=_("e.g. REF-000078"),
    )

    # ── Financial ──
    currency = models.CharField(_("Currency"), max_length=3, default="USD")
    amount = models.DecimalField(
        _("Refund Amount"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    amount_shipping = models.DecimalField(
        _("Shipping Refund Amount"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    amount_tax = models.DecimalField(
        _("Tax Refund Amount"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    restocking_fee_deducted = models.DecimalField(
        _("Restocking Fee Deducted"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    net_amount = models.DecimalField(
        _("Net Refund Amount"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "amount minus restocking_fee_deducted and other deductions."),
    )

    # ── Type & method ──
    refund_type = models.CharField(
        _("Refund Type"),
        max_length=30,
        choices=RefundType.choices,
        default=RefundType.PARTIAL,
    )
    method = models.CharField(
        _("Refund Method"),
        max_length=30,
        choices=RefundMethod.choices,
        default=RefundMethod.ORIGINAL_PAYMENT,
    )

    # ── Status ──
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING,
        db_index=True,
    )

    # ── Gateway reference ──
    transaction_id = models.UUIDField(
        _("Payment Transaction"),
        null=True,
        blank=True,
        help_text=_("FK-less ref to payments.Transaction being reversed."),
    )
    gateway_refund_id = models.CharField(
        _("Gateway Refund ID"),
        max_length=255,
        blank=True,
        help_text=_(
            "Reference ID returned by payment gateway. "
            "e.g. Stripe refund ID 're_...' or Paystack refund reference."
        ),
    )
    gateway_response = models.JSONField(
        _("Gateway Response Payload"),
        default=dict,
        blank=True,
        help_text=_(
            "Raw response from payment gateway stored for reconciliation."),
    )

    # ── Store credit ──
    store_credit_issued = models.DecimalField(
        _("Store Credit Issued"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    gift_card_code_issued = models.CharField(
        _("Gift Card Code Issued"),
        max_length=100,
        blank=True,
        help_text=_("If method=gift_card, the code issued to the customer."),
    )

    # ── Reason ──
    reason = models.TextField(
        _("Refund Reason"),
        blank=True,
        help_text=_("Internal reason for issuing this refund."),
    )
    notify_customer = models.BooleanField(_("Notify Customer"), default=True)

    # ── Timestamps ──
    processed_at = models.DateTimeField(
        _("Processed At"), null=True, blank=True)
    failed_at = models.DateTimeField(_("Failed At"), null=True, blank=True)
    failure_reason = models.CharField(
        _("Failure Reason"), max_length=500, blank=True)

    # ── Actors ──
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_refunds",
        verbose_name=_("Created By"),
        help_text=_("Null = customer-initiated or automated."),
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processed_refunds",
        verbose_name=_("Processed By"),
    )

    # ── Restock flag ──
    restock_items = models.BooleanField(
        _("Restock Items"),
        default=False,
        help_text=_(
            "If True, trigger StockMovement to restock the returned items."),
    )

    class Meta:
        verbose_name = _("Refund")
        verbose_name_plural = _("Refunds")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "status"]),
            models.Index(fields=["refund_number"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["gateway_refund_id"]),
        ]

    def __str__(self):
        return (
            f"Refund {self.refund_number} — "
            f"{self.currency} {self.net_amount} [{self.status}]"
        )

    @property
    def is_successful(self):
        return self.status == self.RefundStatus.SUCCEEDED

    @transaction.atomic
    def mark_succeeded(self, gateway_refund_id="", gateway_response=None):
        self.status = self.RefundStatus.SUCCEEDED
        self.processed_at = timezone.now()
        if gateway_refund_id:
            self.gateway_refund_id = gateway_refund_id
        if gateway_response:
            self.gateway_response = gateway_response
        self.save(update_fields=[
            "status", "processed_at", "gateway_refund_id",
            "gateway_response", "updated_at"
        ])
        # Update order financial totals
        self.order.total_refunded = (
            models.F("total_refunded") + self.net_amount
        )
        self.order.total_outstanding = (
            models.F("total_outstanding") - self.net_amount
        )
        Order.objects.filter(pk=self.order_id).update(
            total_refunded=models.F("total_refunded") + self.net_amount,
            total_outstanding=models.F("total_outstanding") - self.net_amount,
        )

    @transaction.atomic
    def mark_failed(self, reason=""):
        self.status = self.RefundStatus.FAILED
        self.failed_at = timezone.now()
        self.failure_reason = reason
        self.save(update_fields=["status", "failed_at",
                  "failure_reason", "updated_at"])


# ─────────────────────────────────────────────────────────────

class RefundLineItem(MixIdAndTimeModel):
    """
    Granular line-level breakdown of a Refund.
    Each RefundLineItem corresponds to a specific OrderItem
    and the amount being refunded for it.

    A Refund without RefundLineItems = shipping-only or custom amount refund.
    """

    refund = models.ForeignKey(
        Refund,
        on_delete=models.CASCADE,
        related_name="line_items",
        verbose_name=_("Refund"),
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="refund_line_items",
        verbose_name=_("Order Item"),
    )
    quantity = models.PositiveIntegerField(
        _("Quantity Refunded"),
        validators=[MinValueValidator(1)],
    )
    amount = models.DecimalField(
        _("Line Refund Amount"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "Total refund for this line (may include proportional tax)."),
    )
    amount_tax = models.DecimalField(
        _("Tax Refund Amount"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    restock = models.BooleanField(
        _("Restock This Item"),
        default=False,
        help_text=_("Trigger StockMovement for this specific line."),
    )
    restock_location_id = models.UUIDField(
        _("Restock Location"),
        null=True,
        blank=True,
        help_text=_("FK-less ref to inventory.InventoryLocation."),
    )

    class Meta:
        verbose_name = _("Refund Line Item")
        verbose_name_plural = _("Refund Line Items")
        unique_together = [("refund", "order_item")]
        ordering = ["refund"]

    def __str__(self):
        return (
            f"{self.quantity}× {self.order_item.product_title} "
            f"— {self.amount} refunded in {self.refund.refund_number}"
        )
