from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class CartSettings(models.Model):
    """
    Shopping cart behavior and appearance customization.

    CONTROLS:
    - Cart type (page, drawer, popup)
    - Cart behavior and interactions
    - Upsells and cross-sells
    - Discount code handling
    - Progress indicators

    IMPACT:
    - Shopping cart user experience
    - Cart abandonment rate
    - Average order value

    SHOPIFY EQUIVALENT: Theme > Cart
    """

    # === CART TYPE ===
    CART_TYPE_CHOICES = [
        ('page', 'Dedicated Cart Page'),
        ('drawer', 'Slide-out Drawer'),
        ('popup', 'Popup Modal'),
        ('dropdown', 'Dropdown from Header'),
        ('mini', 'Mini Cart Preview'),
    ]
    cart_type = models.CharField(
        max_length=20,
        choices=CART_TYPE_CHOICES,
        default='drawer',
        help_text="Cart display style"
    )

    # === DRAWER SETTINGS ===
    drawer_position = models.CharField(
        max_length=10,
        choices=[('left', 'Left'), ('right', 'Right')],
        default='right',
        help_text="Drawer slide-in position"
    )

    drawer_width = models.IntegerField(
        default=400,
        validators=[MinValueValidator(300), MaxValueValidator(600)],
        help_text="Drawer width in pixels"
    )

    drawer_overlay_opacity = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Background overlay opacity (0-100%)"
    )

    # === CART BEHAVIOR ===
    auto_open_on_add = models.BooleanField(
        default=True,
        help_text="Automatically open cart when item added"
    )

    auto_close_delay = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(30)],
        help_text="Auto-close cart after N seconds (0 = never)"
    )

    show_continue_shopping = models.BooleanField(
        default=True,
        help_text="Show 'Continue Shopping' button"
    )

    enable_cart_notes = models.BooleanField(
        default=True,
        help_text="Allow order notes/special instructions"
    )

    enable_gift_message = models.BooleanField(
        default=False,
        help_text="Allow gift message input"
    )

    enable_gift_wrapping = models.BooleanField(
        default=False,
        help_text="Offer gift wrapping option"
    )

    gift_wrapping_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Gift wrapping fee"
    )

    # === CART ITEMS ===
    show_product_images = models.BooleanField(
        default=True,
        help_text="Show product thumbnails"
    )

    image_size = models.CharField(
        max_length=20,
        choices=[
            ('small', 'Small (60px)'),
            ('medium', 'Medium (80px)'),
            ('large', 'Large (100px)'),
        ],
        default='medium'
    )

    show_variant_details = models.BooleanField(
        default=True,
        help_text="Show variant information (size, color, etc.)"
    )

    show_remove_button = models.BooleanField(
        default=True,
        help_text="Show remove/delete item button"
    )

    enable_quantity_update = models.BooleanField(
        default=True,
        help_text="Allow quantity changes in cart"
    )

    show_unit_price = models.BooleanField(
        default=True,
        help_text="Show individual item price"
    )

    show_line_total = models.BooleanField(
        default=True,
        help_text="Show line item total (price × quantity)"
    )

    # === PRICING DISPLAY ===
    show_item_subtotal = models.BooleanField(
        default=True,
        help_text="Show items subtotal"
    )

    show_savings = models.BooleanField(
        default=True,
        help_text="Show total savings/discounts"
    )

    show_tax_estimate = models.BooleanField(
        default=True,
        help_text="Show estimated tax"
    )

    show_shipping_estimate = models.BooleanField(
        default=True,
        help_text="Show estimated shipping cost"
    )

    show_grand_total = models.BooleanField(
        default=True,
        help_text="Show final total"
    )

    # === UPSELLS & CROSS-SELLS ===
    enable_cart_upsells = models.BooleanField(
        default=False,
        help_text="Show product recommendations in cart"
    )

    upsell_title = models.CharField(
        max_length=100,
        default='Frequently Bought Together'
    )

    upsell_count = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="Number of upsell products to show"
    )

    upsell_algorithm = models.CharField(
        max_length=20,
        choices=[
            ('related', 'Related Products'),
            ('frequently_bought', 'Frequently Bought Together'),
            ('bestsellers', 'Best Sellers'),
            ('manual', 'Manual Selection'),
        ],
        default='frequently_bought'
    )

    # === FREE SHIPPING PROGRESS ===
    show_free_shipping_progress = models.BooleanField(
        default=True,
        help_text="Show progress bar for free shipping threshold"
    )

    free_shipping_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('50.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Free shipping minimum order amount"
    )

    progress_bar_color = models.CharField(
        max_length=7,
        default='#10B981',
        help_text="Progress bar color (hex)"
    )

    progress_message_below = models.CharField(
        max_length=200,
        default='Add {amount} more to get FREE shipping!',
        help_text="Message when below threshold (use {amount} placeholder)"
    )

    progress_message_reached = models.CharField(
        max_length=200,
        default='You qualify for FREE shipping!',
        help_text="Message when threshold reached"
    )

    # === DISCOUNT CODES ===
    show_discount_code_field = models.BooleanField(
        default=True,
        help_text="Show discount/promo code input"
    )

    discount_code_placeholder = models.CharField(
        max_length=50,
        default='Enter discount code'
    )

    discount_code_position = models.CharField(
        max_length=20,
        choices=[
            ('top', 'Top of Cart'),
            ('bottom', 'Bottom of Cart'),
            ('collapsed', 'Collapsed/Hidden by Default'),
        ],
        default='bottom'
    )

    # === CHECKOUT BUTTON ===
    checkout_button_text = models.CharField(
        max_length=50,
        default='Proceed to Checkout'
    )

    checkout_button_style = models.CharField(
        max_length=20,
        choices=[
            ('primary', 'Primary Button'),
            ('large', 'Large Prominent Button'),
            ('full_width', 'Full Width Button'),
        ],
        default='full_width'
    )

    show_secure_checkout_badge = models.BooleanField(
        default=True,
        help_text="Show 'Secure Checkout' badge/icon"
    )

    show_accepted_payments = models.BooleanField(
        default=True,
        help_text="Show accepted payment method icons"
    )

    show_money_back_guarantee = models.BooleanField(
        default=False,
        help_text="Show money-back guarantee badge"
    )

    # === EMPTY CART ===
    empty_cart_message = models.CharField(
        max_length=200,
        default='Your cart is empty'
    )

    empty_cart_icon = models.CharField(
        max_length=50,
        default='shopping-cart',
        help_text="Icon to show for empty cart"
    )

    show_continue_shopping_on_empty = models.BooleanField(
        default=True,
        help_text="Show 'Continue Shopping' button when cart empty"
    )

    show_popular_products_on_empty = models.BooleanField(
        default=True,
        help_text="Show popular products when cart is empty"
    )

    popular_products_count = models.IntegerField(
        default=4,
        validators=[MinValueValidator(2), MaxValueValidator(12)]
    )

    # === CART EXPIRY ===
    enable_cart_expiry = models.BooleanField(
        default=True,
        help_text="Automatically clear old cart items"
    )

    cart_expiry_days = models.IntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Days before cart items expire"
    )

    show_expiry_warning = models.BooleanField(
        default=True,
        help_text="Warn users about expiring cart items"
    )

    # === STOCK WARNINGS ===
    show_low_stock_warning = models.BooleanField(
        default=True,
        help_text="Show warning for low stock items in cart"
    )

    show_out_of_stock_warning = models.BooleanField(
        default=True,
        help_text="Show warning for out of stock items"
    )

    auto_remove_out_of_stock = models.BooleanField(
        default=False,
        help_text="Automatically remove out of stock items"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cart_settings'
        verbose_name = 'Cart Setting'
        verbose_name_plural = 'Cart Settings'

    def __str__(self):
        return "Cart Settings"

    def clean(self):
        errors = {}

        if self.free_shipping_threshold < 0:
            errors['free_shipping_threshold'] = "Free shipping threshold cannot be negative."

        if self.gift_wrapping_price < 0:
            errors['gift_wrapping_price'] = "Gift wrapping price cannot be negative."

        if errors:
            raise ValidationError(errors)
