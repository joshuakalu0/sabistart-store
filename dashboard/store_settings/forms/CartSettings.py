import logging
import re
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import CartSettings

logger = logging.getLogger(__name__)


class CartSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Cart Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = CartSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === CART TYPE ===
            'cart_type': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # === DRAWER SETTINGS ===
            'drawer_position': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'drawer_width': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 300,
                'max': 600
            }),
            'drawer_overlay_opacity': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 0,
                'max': 100
            }),

            # === CART BEHAVIOR ===
            'auto_open_on_add': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'auto_close_delay': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 0,
                'max': 30
            }),
            'show_continue_shopping': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'enable_cart_notes': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'enable_gift_message': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'enable_gift_wrapping': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'gift_wrapping_price': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'step': '0.01',
                'min': '0'
            }),

            # === CART ITEMS ===
            'show_product_images': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'image_size': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_variant_details': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_remove_button': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'enable_quantity_update': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_unit_price': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_line_total': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === PRICING DISPLAY ===
            'show_item_subtotal': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_savings': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_tax_estimate': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_shipping_estimate': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_grand_total': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === UPSELLS & CROSS-SELLS ===
            'enable_cart_upsells': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'upsell_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Frequently Bought Together'
            }),
            'upsell_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 6
            }),
            'upsell_algorithm': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # === FREE SHIPPING PROGRESS ===
            'show_free_shipping_progress': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'free_shipping_threshold': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'step': '0.01',
                'min': '0'
            }),
            'progress_bar_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'progress_message_below': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Add {amount} more to get FREE shipping!'
            }),
            'progress_message_reached': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'You qualify for FREE shipping!'
            }),

            # === DISCOUNT CODES ===
            'show_discount_code_field': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'discount_code_placeholder': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Enter discount code'
            }),
            'discount_code_position': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # === CHECKOUT BUTTON ===
            'checkout_button_text': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Proceed to Checkout'
            }),
            'checkout_button_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_secure_checkout_badge': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_accepted_payments': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_money_back_guarantee': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === EMPTY CART ===
            'empty_cart_message': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Your cart is empty'
            }),
            'empty_cart_icon': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'shopping-cart'
            }),
            'show_continue_shopping_on_empty': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_popular_products_on_empty': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'popular_products_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 2,
                'max': 12
            }),

            # === CART EXPIRY ===
            'enable_cart_expiry': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cart_expiry_days': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 365
            }),
            'show_expiry_warning': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === STOCK WARNINGS ===
            'show_low_stock_warning': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_out_of_stock_warning': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'auto_remove_out_of_stock': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
        }

    def clean_drawer_width(self):
        """Validate drawer width range."""
        width = self.cleaned_data.get('drawer_width')
        if width and not (300 <= width <= 600):
            raise ValidationError(
                _("Drawer width must be between 300 and 600 pixels."))
        return width

    def clean_drawer_overlay_opacity(self):
        """Validate overlay opacity range."""
        opacity = self.cleaned_data.get('drawer_overlay_opacity')
        if opacity and not (0 <= opacity <= 100):
            raise ValidationError(
                _("Overlay opacity must be between 0 and 100."))
        return opacity

    def clean_auto_close_delay(self):
        """Validate auto-close delay range."""
        delay = self.cleaned_data.get('auto_close_delay')
        if delay and not (0 <= delay <= 30):
            raise ValidationError(
                _("Auto-close delay must be between 0 and 30 seconds."))
        return delay

    def clean_gift_wrapping_price(self):
        """Validate gift wrapping price is non-negative."""
        price = self.cleaned_data.get('gift_wrapping_price')
        if price and price < 0:
            raise ValidationError(_("Gift wrapping price cannot be negative."))
        return price

    def clean_free_shipping_threshold(self):
        """Validate free shipping threshold is non-negative."""
        threshold = self.cleaned_data.get('free_shipping_threshold')
        if threshold and threshold < 0:
            raise ValidationError(
                _("Free shipping threshold cannot be negative."))
        return threshold

    def clean_upsell_count(self):
        """Validate upsell count range."""
        count = self.cleaned_data.get('upsell_count')
        if count and not (1 <= count <= 6):
            raise ValidationError(_("Upsell count must be between 1 and 6."))
        return count

    def clean_popular_products_count(self):
        """Validate popular products count range."""
        count = self.cleaned_data.get('popular_products_count')
        if count and not (2 <= count <= 12):
            raise ValidationError(
                _("Popular products count must be between 2 and 12."))
        return count

    def clean_cart_expiry_days(self):
        """Validate cart expiry days range."""
        days = self.cleaned_data.get('cart_expiry_days')
        if days and not (1 <= days <= 365):
            raise ValidationError(
                _("Cart expiry days must be between 1 and 365."))
        return days

    def clean_progress_bar_color(self):
        """Validate progress bar color hex format."""
        color = self.cleaned_data.get('progress_bar_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #10B981)."))
        return color

    def clean_progress_message_below(self):
        """Validate progress message contains placeholder."""
        message = self.cleaned_data.get('progress_message_below')
        if message and '{amount}' not in message:
            logger.warning(
                "Progress message below threshold does not contain {amount} placeholder")
        return message

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === Cart Type Logic ===
        cart_type = cleaned_data.get('cart_type')
        drawer_position = cleaned_data.get('drawer_position')
        drawer_width = cleaned_data.get('drawer_width')
        overlay_opacity = cleaned_data.get('drawer_overlay_opacity')

        if cart_type != 'drawer':
            logger.info(
                f"Cart type is '{cart_type}' - drawer settings will be ignored")

        # === Gift Wrapping Logic ===
        enable_gift_wrapping = cleaned_data.get('enable_gift_wrapping')
        gift_wrapping_price = cleaned_data.get('gift_wrapping_price')

        if enable_gift_wrapping and gift_wrapping_price == 0:
            logger.info(
                "Gift wrapping enabled but price is $0 - may be intentional for free gift wrapping")

        # === Free Shipping Progress Logic ===
        show_progress = cleaned_data.get('show_free_shipping_progress')
        threshold = cleaned_data.get('free_shipping_threshold')

        if show_progress and threshold == 0:
            self.add_error(
                'free_shipping_threshold',
                _("Free shipping threshold must be greater than 0 when progress bar is enabled.")
            )

        # === Upsells Logic ===
        enable_upsells = cleaned_data.get('enable_cart_upsells')
        upsell_count = cleaned_data.get('upsell_count')

        if enable_upsells and not upsell_count:
            self.add_error(
                'upsell_count',
                _("Upsell count is required when cart upsells are enabled.")
            )

        # === Discount Code Logic ===
        show_discount = cleaned_data.get('show_discount_code_field')
        discount_placeholder = cleaned_data.get('discount_code_placeholder')

        if show_discount and not discount_placeholder:
            logger.warning(
                "Discount code field enabled but no placeholder text provided")

        # === Empty Cart Logic ===
        show_popular = cleaned_data.get('show_popular_products_on_empty')
        popular_count = cleaned_data.get('popular_products_count')

        if show_popular and not popular_count:
            self.add_error(
                'popular_products_count',
                _("Popular products count is required when showing popular products on empty cart.")
            )

        # === Cart Expiry Logic ===
        enable_expiry = cleaned_data.get('enable_cart_expiry')
        expiry_days = cleaned_data.get('cart_expiry_days')
        show_warning = cleaned_data.get('show_expiry_warning')

        if enable_expiry and not expiry_days:
            self.add_error(
                'cart_expiry_days',
                _("Cart expiry days is required when cart expiry is enabled.")
            )

        if show_warning and not enable_expiry:
            logger.warning(
                "Expiry warning enabled but cart expiry is disabled")

        # === Stock Warnings Logic ===
        auto_remove = cleaned_data.get('auto_remove_out_of_stock')
        show_out_of_stock = cleaned_data.get('show_out_of_stock_warning')

        if auto_remove and show_out_of_stock:
            logger.info(
                "Both auto-remove and show warning enabled for out of stock - auto-remove will take precedence")

        # === Conversion Optimization Warnings ===
        if not cleaned_data.get('show_free_shipping_progress'):
            logger.warning(
                "Free shipping progress bar disabled - may impact average order value")

        if not cleaned_data.get('enable_cart_upsells'):
            logger.info(
                "Cart upsells disabled - may impact average order value")

        if not cleaned_data.get('show_discount_code_field'):
            logger.info(
                "Discount code field disabled - may impact conversion for promo users")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"CartSettings saved (cart_type: {instance.cart_type}, upsells: {instance.enable_cart_upsells})"
        )
        return instance
