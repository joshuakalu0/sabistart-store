from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal
import uuid
from dashboard.settings.models import AuditModel
from public.userauth.models.tenant_user import TenantUser


class Store(AuditModel):
    """Physical POS checkout locations within the tenant's main store."""
    STATUS_CHOICES = [
        ("active", _("Active")),
        ("inactive", _("Inactive")),
        ("maintenance", _("Maintenance")),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, db_index=True)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    address = models.TextField()
    contact_name = models.CharField(max_length=160, blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    contact_email = models.EmailField(blank=True)
    manager = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_stores')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.0000'))
    is_active = models.BooleanField(default=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", db_index=True)
    
    class Meta:
        db_table = 'pos_stores'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def branch_code(self):
        return self.code


class POSCatalogItem(AuditModel):
    """Bridge a POS sellable item to the tenant's real product catalog."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="pos_catalog_items",
    )
    variant = models.ForeignKey(
        "product.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_catalog_items",
    )
    label_override = models.CharField(max_length=255, blank=True)
    barcode_override = models.CharField(max_length=100, blank=True, db_index=True)
    quick_add_code = models.CharField(max_length=50, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    allow_open_quantity = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "pos_catalog_items"
        ordering = ["product__name", "variant__sku"]
        unique_together = [["product", "variant"]]

    def clean(self):
        if self.variant_id and self.variant and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "Selected variant must belong to the selected product."})

    @property
    def display_name(self):
        if self.label_override:
            return self.label_override
        if self.variant and self.variant.variant_name:
            return f"{self.product.name} - {self.variant.variant_name}"
        return self.product.name

    @property
    def display_sku(self):
        if self.variant and self.variant.sku:
            return self.variant.sku
        return self.product.sku

    @property
    def display_barcode(self):
        if self.barcode_override:
            return self.barcode_override
        if self.variant and self.variant.barcode:
            return self.variant.barcode
        return ""

    @property
    def base_cost_price(self):
        if self.variant and self.variant.cost_price is not None:
            return self.variant.cost_price
        return self.product.cost_price or Decimal("0.00")

    @property
    def base_selling_price(self):
        if self.variant and self.variant.price is not None:
            return self.variant.price
        return self.product.price or Decimal("0.00")

    @property
    def is_taxable(self):
        return self.product.tax_status != "none"

    def __str__(self):
        return self.display_name


class POSProduct(AuditModel):
    """POS-specific products - independent inventory system"""
    
    PRODUCT_TYPE = [
        ('simple', _('Simple Product')),
        ('service', _('Service')),
        ('bundle', _('Bundle')),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Basic Info
    name = models.CharField(max_length=500, db_index=True)
    image = models.ImageField(upload_to='pos/products/%Y/%m/', blank=True, null=True)
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    barcode = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Product details
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE, default='simple')
    description = models.TextField(blank=True)
    
    # Pricing
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    # Tax
    is_taxable = models.BooleanField(default=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    
    # Category
    category = models.CharField(max_length=100, blank=True, db_index=True)
    brand = models.CharField(max_length=100, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        db_table = 'pos_products'
        ordering = ['name']
        indexes = [
            models.Index(fields=['sku', 'is_active']),
            models.Index(fields=['barcode']),
            models.Index(fields=['category', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.sku})"


class StoreInventory(AuditModel):
    """Location-specific inventory for legacy POS products or bridged catalog items."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='inventory')
    product = models.ForeignKey(POSProduct, on_delete=models.CASCADE, related_name='store_inventory', null=True, blank=True)
    catalog_item = models.ForeignKey(
        POSCatalogItem,
        on_delete=models.CASCADE,
        related_name="inventory_records",
        null=True,
        blank=True,
    )
    
    # Inventory tracking
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reserved_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    # Store-specific settings
    location = models.CharField(max_length=100, blank=True, help_text="Aisle, shelf location")
    low_stock_threshold = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    
    # Store-specific pricing (overrides product pricing)
    store_cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    store_selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Tracking
    last_restocked = models.DateTimeField(null=True, blank=True, db_index=True)
    last_sold = models.DateTimeField(null=True, blank=True, db_index=True)
    
    class Meta:
        db_table = 'pos_store_inventory'
        indexes = [
            models.Index(fields=['store', 'quantity']),
            models.Index(fields=['quantity', 'low_stock_threshold']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(product__isnull=False) & Q(catalog_item__isnull=True))
                    | (Q(product__isnull=True) & Q(catalog_item__isnull=False))
                ),
                name="pos_inventory_requires_one_item_source",
            ),
            models.UniqueConstraint(
                fields=["store", "product"],
                condition=Q(product__isnull=False),
                name="pos_unique_store_legacy_product",
            ),
            models.UniqueConstraint(
                fields=["store", "catalog_item"],
                condition=Q(catalog_item__isnull=False),
                name="pos_unique_store_catalog_item",
            ),
        ]

    def clean(self):
        if bool(self.product_id) == bool(self.catalog_item_id):
            raise ValidationError("Inventory rows must point to exactly one source item.")
    
    @property
    def available_quantity(self):
        return max(0, self.quantity - self.reserved_quantity)
    
    @property
    def effective_cost_price(self):
        if self.store_cost_price is not None:
            return self.store_cost_price
        if self.catalog_item is not None:
            return self.catalog_item.base_cost_price
        return self.product.cost_price if self.product is not None else Decimal("0.00")

    @property
    def effective_selling_price(self):
        if self.store_selling_price is not None:
            return self.store_selling_price
        if self.catalog_item is not None:
            return self.catalog_item.base_selling_price
        return self.product.selling_price if self.product is not None else Decimal("0.00")

    @property
    def display_name(self):
        if self.catalog_item is not None:
            return self.catalog_item.display_name
        return self.product.name if self.product is not None else "Unknown item"

    @property
    def display_sku(self):
        if self.catalog_item is not None:
            return self.catalog_item.display_sku
        return self.product.sku if self.product is not None else ""

    @property
    def display_barcode(self):
        if self.catalog_item is not None:
            return self.catalog_item.display_barcode
        return self.product.barcode if self.product is not None else ""

    @property
    def is_taxable(self):
        if self.catalog_item is not None:
            return self.catalog_item.is_taxable
        return self.product.is_taxable if self.product is not None else False

    def __str__(self):
        return f"{self.store.name}: {self.display_name} ({self.quantity})"


class POSTerminal(AuditModel):
    """Physical browser/printer register definition for a POS place."""

    TERMINAL_TYPE = [
        ("browser", _("Browser / Web POS")),
        ("escpos", _("ESC/POS Printer")),
        ("network", _("Network Printer")),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="terminals")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    notes = models.TextField(blank=True)
    terminal_type = models.CharField(max_length=20, choices=TERMINAL_TYPE, default="browser")
    printer_identifier = models.CharField(max_length=255, blank=True)
    receipt_header = models.TextField(blank=True)
    receipt_footer = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pos_terminals"
        ordering = ["store__name", "name"]

    def __str__(self):
        return f"{self.store.name} - {self.name}"


class POSSession(AuditModel):
    """Cashier session lifecycle for a POS location."""

    SESSION_STATUS = [
        ("open", _("Open")),
        ("closed", _("Closed")),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="sessions")
    terminal = models.ForeignKey(POSTerminal, on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions")
    cashier = models.ForeignKey(TenantUser, on_delete=models.CASCADE, related_name="pos_sessions")
    status = models.CharField(max_length=20, choices=SESSION_STATUS, default="open", db_index=True)
    opened_at = models.DateTimeField(default=timezone.now, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    closing_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    shortage_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    overage_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "pos_sessions"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"{self.store.name} - {self.cashier} ({self.status})"


class InventoryAdjustment(AuditModel):
    """Track inventory adjustments"""
    ADJUSTMENT_TYPE = [
        ('restock', _('Restock')),
        ('sale', _('Sale')),
        ('damage', _('Damage/Loss')),
        ('reconciliation', _('Reconciliation')),
        ('transfer', _('Transfer')),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store_inventory = models.ForeignKey(StoreInventory, on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE, db_index=True)
    quantity_before = models.IntegerField(validators=[MinValueValidator(0)])
    quantity_change = models.IntegerField()
    quantity_after = models.IntegerField(validators=[MinValueValidator(0)])
    reason = models.TextField()
    reference_number = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'pos_inventory_adjustments'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.store_inventory} - {self.get_adjustment_type_display()} ({self.quantity_change:+d})"





class POSTransaction(AuditModel):
    """Main POS transaction record"""
    
    TRANSACTION_TYPE = [
        ('sale', _('Sale')),
        ('refund', _('Refund')),
        ('void', _('Void')),
        ('exchange', _('Exchange')),
    ]
    
    TRANSACTION_STATUS = [
        ('pending', _('Pending')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
        ('refunded', _('Refunded')),
        ('partially_refunded', _('Partially Refunded')),
    ]

    ORIGIN_MODE = [
        ("online", _("Online")),
        ("offline", _("Offline")),
        ("synced", _("Synced Offline")),
    ]

    SYNC_STATUS = [
        ("not_required", _("Not Required")),
        ("queued", _("Queued")),
        ("synced", _("Synced")),
        ("failed", _("Failed")),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='transactions')
    cashier = models.ForeignKey(TenantUser, on_delete=models.CASCADE, related_name='pos_transactions')
    session = models.ForeignKey(POSSession, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions")
    terminal = models.ForeignKey(POSTerminal, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions")
    authoritative_order = models.ForeignKey(
        "cart.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_transactions",
    )
    
    # Transaction details
    transaction_number = models.CharField(max_length=50, unique=True, db_index=True)
    client_transaction_id = models.CharField(max_length=80, blank=True, db_index=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE, default='sale', db_index=True)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='pending', db_index=True)
    origin_mode = models.CharField(max_length=20, choices=ORIGIN_MODE, default="online", db_index=True)
    sync_status = models.CharField(max_length=20, choices=SYNC_STATUS, default="not_required", db_index=True)
    
    # Customer info (optional)
    customer_name = models.CharField(max_length=200, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    
    # Financial details
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    # Payment tracking
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    change_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # References
    original_transaction = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='related_transactions')
    
    # Metadata
    notes = models.TextField(blank=True)
    receipt_printed = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'pos_transactions'
        verbose_name = _('POS Transaction')
        verbose_name_plural = _('POS Transactions')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'status']),
            models.Index(fields=['transaction_type', 'status']),
            models.Index(fields=['created_at', 'status']),
        ]
    
    def __str__(self):
        return f"Transaction {self.transaction_number} - ${self.total_amount}"


class POSTransactionItem(AuditModel):
    """Individual items in a POS transaction"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(POSTransaction, on_delete=models.CASCADE, related_name='items')
    store_inventory = models.ForeignKey(StoreInventory, on_delete=models.CASCADE, related_name='transaction_items')
    catalog_item = models.ForeignKey(POSCatalogItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="transaction_items")
    
    # Product details (stored for historical accuracy)
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=100, blank=True)
    product_barcode = models.CharField(max_length=100, blank=True)
    
    # Pricing
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    quantity = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    # Tax details
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.0000'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    class Meta:
        db_table = 'pos_transaction_items'
        verbose_name = _('Transaction Item')
        verbose_name_plural = _('Transaction Items')
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class POSPayment(AuditModel):
    """Payment records for POS transactions"""
    
    PAYMENT_METHOD = [
        ('cash', _('Cash')),
        ('bank_transfer', _('Bank Transfer')),
        ('card_terminal', _('POS Terminal / Card')),
        ('split', _('Split Payment')),
        ('mobile_money', _('Mobile Money')),
        ('custom', _('Custom Payment Method')),
    ]
    
    PAYMENT_STATUS = [
        ('pending', _('Pending')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('refunded', _('Refunded')),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(POSTransaction, on_delete=models.CASCADE, related_name='payments')
    
    # Payment details
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending', db_index=True)
    
    # Card/Electronic payment details
    card_last_four = models.CharField(max_length=4, blank=True)
    card_type = models.CharField(max_length=20, blank=True)
    authorization_code = models.CharField(max_length=50, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=120, blank=True)
    terminal_reference = models.CharField(max_length=100, blank=True)
    custom_payment_label = models.CharField(max_length=120, blank=True)
    amount_received = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    balance_returned = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Processing details
    processed_at = models.DateTimeField(null=True, blank=True)
    processor_response = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'pos_payments'
        verbose_name = _('POS Payment')
        verbose_name_plural = _('POS Payments')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction', 'status']),
            models.Index(fields=['payment_method', 'status']),
        ]
    
    def __str__(self):
        return f"{self.get_payment_method_display()} - ${self.amount}"


class POSDiscount(AuditModel):
    """Discount management for POS"""
    
    DISCOUNT_TYPE = [
        ('percentage', _('Percentage')),
        ('fixed', _('Fixed Amount')),
        ('bogo', _('Buy One Get One')),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE, db_index=True)
    
    # Discount values
    percentage_value = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fixed_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Conditions
    minimum_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    maximum_discount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Validity
    valid_from = models.DateTimeField(db_index=True)
    valid_until = models.DateTimeField(db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Usage tracking
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'pos_discounts'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"


# ─────────────────────────────────────────────────────────────
# SERVER-SIDE CART (persistent, price-snapshotted)
# ─────────────────────────────────────────────────────────────

class POSCart(models.Model):
    """
    A server-side cart that persists between product selection and checkout.

    One OPEN cart is kept per cashier per store. When checkout succeeds the
    cart is marked COMPLETED and pinned to its resulting POSTransaction. The
    next call to get_or_create_active_cart() will then create a fresh OPEN
    cart automatically.

    Prices are NOT stored on the cart itself — they are locked into each
    POSCartItem at the moment the item is added (price snapshot pattern).
    """

    class Status(models.TextChoices):
        OPEN      = "open",      _("Open")
        HELD      = "held",      _("Held")
        COMPLETED = "completed", _("Completed")
        VOIDED    = "voided",    _("Voided")

    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store     = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name="pos_carts",
    )
    cashier   = models.ForeignKey(
        "userauth.TenantUser", on_delete=models.CASCADE, related_name="pos_carts",
    )
    session_id = models.UUIDField(
        null=True, blank=True,
        verbose_name=_("Session ID"),
        help_text=_("UUID of the related POSSession (soft reference — no DB-level FK constraint)."),
    )
    status    = models.CharField(
        max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True,
    )
    # Linked after a successful checkout
    transaction = models.OneToOneField(
        POSTransaction, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="source_cart",
    )
    hold_reference = models.CharField(max_length=80, blank=True, db_index=True)
    held_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    voided_at    = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pos_cart"
        verbose_name = _("POS Cart")
        verbose_name_plural = _("POS Carts")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["cashier", "store", "status"]),
            models.Index(fields=["store", "status"]),
        ]

    def __str__(self) -> str:
        return f"Cart {self.id} [{self.status}] — {self.store.name}"

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN

    @property
    def item_count(self) -> int:
        return self.items.count()

    @property
    def subtotal(self):
        from decimal import Decimal
        return sum(item.line_total for item in self.items.all()) or Decimal("0.00")


class POSCartItem(models.Model):
    """
    One line in a POSCart.

    ``unit_price`` is snapshotted from the StoreInventory at add-time so that
    subsequent price changes do not silently alter the cashier's pending order.
    ``line_total`` is always ``unit_price × quantity`` (re-computed on save).
    """

    id    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart  = models.ForeignKey(POSCart, on_delete=models.CASCADE, related_name="items")

    # Source references (one or both may be set depending on product type)
    store_inventory = models.ForeignKey(
        StoreInventory, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="cart_items",
    )
    catalog_item = models.ForeignKey(
        POSCatalogItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="cart_items",
    )

    # Denormalised snapshot fields — these NEVER change after being set
    product_name = models.CharField(_("Product Name"), max_length=255)
    product_sku  = models.CharField(_("SKU"), max_length=100, blank=True)
    unit_price   = models.DecimalField(
        _("Unit Price (snapshot)"), max_digits=12, decimal_places=2,
    )
    quantity   = models.PositiveIntegerField(_("Quantity"), default=1)
    line_total = models.DecimalField(
        _("Line Total"), max_digits=14, decimal_places=2, default=0,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pos_cart_item"
        verbose_name = _("POS Cart Item")
        verbose_name_plural = _("POS Cart Items")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.product_name} × {self.quantity} @ {self.unit_price}"

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)
