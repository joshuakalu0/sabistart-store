import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import ProductPageSettings

logger = logging.getLogger(__name__)


class ProductPageSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Product Page Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = ProductPageSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === LAYOUT ===
            'layout': forms.Select(attrs={'class': 'form-select'}),

            # === IMAGE GALLERY ===
            'gallery_style': forms.Select(attrs={'class': 'form-select'}),
            'enable_image_zoom': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_lightbox': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_360_view': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_video_in_gallery': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'image_aspect_ratio': forms.Select(attrs={'class': 'form-select'}),

            # === PRODUCT INFO ===
            'show_vendor': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_sku': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_availability': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_stock_quantity': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'low_stock_threshold': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 100
            }),
            'show_product_type': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_tags': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_share_buttons': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === VARIANTS ===
            'variant_display': forms.Select(attrs={'class': 'form-select'}),
            'show_variant_images': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_variant_prices': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === PRICING ===
            'show_price_per_unit': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_savings_amount': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_savings_percentage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_bulk_pricing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_tax_info': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === QUANTITY SELECTOR ===
            'quantity_selector_style': forms.Select(attrs={'class': 'form-select'}),
            'min_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1
            }),
            'max_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1
            }),
            'quantity_increments': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1
            }),

            # === ADD TO CART ===
            'add_to_cart_button_text': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Add to Cart'
            }),
            'show_buy_now_button': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'buy_now_button_text': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Buy Now'
            }),
            'enable_sticky_add_to_cart': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_quantity_in_sticky_bar': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === TABS/ACCORDION ===
            'description_display': forms.Select(attrs={'class': 'form-select'}),
            'show_description_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_specifications_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_shipping_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_reviews_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_questions_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === TRUST SIGNALS ===
            'show_trust_badges': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_secure_checkout_badge': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_money_back_guarantee': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_free_shipping_badge': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_warranty_info': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'trust_badge_position': forms.Select(attrs={'class': 'form-select'}),

            # === RELATED PRODUCTS ===
            'show_related_products': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'related_products_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'You May Also Like'
            }),
            'related_products_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 2,
                'max': 12
            }),
            'related_products_algorithm': forms.Select(attrs={'class': 'form-select'}),

            # === RECENTLY VIEWED ===
            'show_recently_viewed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'recently_viewed_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Recently Viewed'
            }),
            'recently_viewed_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 2,
                'max': 12
            }),

            # === BREADCRUMBS ===
            'show_breadcrumbs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'breadcrumb_style': forms.Select(attrs={'class': 'form-select'}),

            # === WISHLIST & COMPARE ===
            'show_wishlist_button': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_compare_button': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === DELIVERY INFO ===
            'show_estimated_delivery': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_shipping_calculator': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_store_pickup_option': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_low_stock_threshold(self):
        """Validate low stock threshold range."""
        threshold = self.cleaned_data.get('low_stock_threshold')
        if threshold and not (1 <= threshold <= 100):
            raise ValidationError(
                _("Low stock threshold must be between 1 and 100."))
        return threshold

    def clean_min_quantity(self):
        """Validate minimum quantity."""
        min_qty = self.cleaned_data.get('min_quantity')
        if min_qty and min_qty < 1:
            raise ValidationError(_("Minimum quantity must be at least 1."))
        return min_qty

    def clean_max_quantity(self):
        """Validate maximum quantity."""
        max_qty = self.cleaned_data.get('max_quantity')
        if max_qty and max_qty < 1:
            raise ValidationError(_("Maximum quantity must be at least 1."))
        return max_qty

    def clean_quantity_increments(self):
        """Validate quantity increments."""
        increments = self.cleaned_data.get('quantity_increments')
        if increments and increments < 1:
            raise ValidationError(_("Quantity increments must be at least 1."))
        return increments

    def clean_related_products_count(self):
        """Validate related products count range."""
        count = self.cleaned_data.get('related_products_count')
        if count and not (2 <= count <= 12):
            raise ValidationError(
                _("Related products count must be between 2 and 12."))
        return count

    def clean_recently_viewed_count(self):
        """Validate recently viewed count range."""
        count = self.cleaned_data.get('recently_viewed_count')
        if count and not (2 <= count <= 12):
            raise ValidationError(
                _("Recently viewed count must be between 2 and 12."))
        return count

    def clean(self):
        """Cross-field validation for quantity settings."""
        cleaned_data = super().clean()

        min_qty = cleaned_data.get('min_quantity')
        max_qty = cleaned_data.get('max_quantity')
        increments = cleaned_data.get('quantity_increments')

        # Min cannot exceed max
        if min_qty and max_qty and min_qty > max_qty:
            raise ValidationError({
                'min_quantity': _("Minimum quantity cannot exceed maximum quantity."),
                'max_quantity': _("Maximum quantity cannot be less than minimum quantity.")
            })

        # Increments cannot exceed max
        if increments and max_qty and increments > max_qty:
            raise ValidationError({
                'quantity_increments': _("Quantity increment cannot exceed maximum quantity.")
            })

        # If Buy Now is enabled, Add to Cart should probably be enabled too
        buy_now = cleaned_data.get('show_buy_now_button')
        if buy_now:
            logger.info(
                "Buy Now button enabled - ensure checkout flow is configured")

        # If sticky add to cart is disabled, quantity in sticky bar is irrelevant
        sticky_cart = cleaned_data.get('enable_sticky_add_to_cart')
        quantity_in_sticky = cleaned_data.get('show_quantity_in_sticky_bar')
        if not sticky_cart and quantity_in_sticky:
            logger.warning(
                "Quantity in sticky bar enabled but sticky cart is disabled")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"ProductPageSettings saved (tenant schema: {instance._meta.db_table})"
        )
        return instance
