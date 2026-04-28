from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class CheckoutSettings(models.Model):
    """
    Customize checkout process and flow.

    CONTROLS:
    - Checkout steps
    - Field requirements
    - Payment/shipping options display
    - Order confirmation

    IMPACT:
    - Checkout user experience
    - Conversion rate
    - Order completion

    SHOPIFY EQUIVALENT: Settings > Checkout
    """

    # === CHECKOUT FLOW ===
    CHECKOUT_STYLE_CHOICES = [
        ('single_page', 'Single Page Checkout'),
        ('multi_step', 'Multi-Step Checkout'),
        ('accordion', 'Accordion Style'),
    ]

    checkout_style = models.CharField(
        max_length=20,
        choices=CHECKOUT_STYLE_CHOICES,
        default='multi_step'
    )

    show_breadcrumbs = models.BooleanField(
        default=True,
        help_text="Show checkout progress steps"
    )

    show_order_summary = models.BooleanField(
        default=True,
        help_text="Show order summary sidebar"
    )

    order_summary_collapsible = models.BooleanField(
        default=True,
        help_text="Allow collapsing order summary on mobile"
    )

    # === CUSTOMER INFORMATION ===
    require_account_creation = models.BooleanField(
        default=False,
        help_text="Force customers to create account"
    )

    allow_guest_checkout = models.BooleanField(
        default=True,
        help_text="Allow checkout without account"
    )

    show_newsletter_signup = models.BooleanField(
        default=True,
        help_text="Show newsletter checkbox at checkout"
    )

    newsletter_opt_in_default = models.BooleanField(
        default=False,
        help_text="Newsletter checkbox checked by default"
    )

    # === ADDRESS FIELDS ===
    require_phone_number = models.BooleanField(default=True)
    require_company_name = models.BooleanField(default=False)
    require_address_line2 = models.BooleanField(default=False)

    show_delivery_instructions = models.BooleanField(
        default=True,
        help_text="Allow delivery notes/instructions"
    )

    # === SHIPPING ===
    show_shipping_calculator = models.BooleanField(
        default=True,
        help_text="Show shipping cost calculator in cart"
    )

    group_shipping_methods = models.BooleanField(
        default=True,
        help_text="Group by carrier/speed"
    )

    # === PAYMENT ===
    show_payment_icons = models.BooleanField(
        default=True,
        help_text="Show accepted payment method icons"
    )

    show_trust_badges = models.BooleanField(
        default=True,
        help_text="Show security/SSL badges"
    )

    # === CART ===
    enable_cart_notes = models.BooleanField(
        default=True,
        help_text="Allow order notes in cart"
    )

    enable_coupon_codes = models.BooleanField(
        default=True,
        help_text="Allow discount codes"
    )

    show_estimated_total = models.BooleanField(
        default=True,
        help_text="Show estimated total before checkout"
    )

    # === CONFIRMATION PAGE ===
    show_related_products = models.BooleanField(
        default=True,
        help_text="Show product recommendations on thank you page"
    )

    show_social_sharing = models.BooleanField(
        default=False,
        help_text="Allow sharing purchase on social media"
    )

    thank_you_message = models.TextField(
        blank=True,
        max_length=500,
        help_text="Custom message on order confirmation"
    )

    # === LEGAL ===
    show_terms_checkbox = models.BooleanField(
        default=True,
        help_text="Require accepting terms & conditions"
    )

    terms_checkbox_text = models.CharField(
        max_length=200,
        default="I agree to the Terms & Conditions"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'checkout_settings'
        verbose_name = 'Checkout Setting'
        verbose_name_plural = 'Checkout Settings'

    def __str__(self):
        return "Checkout Settings"


