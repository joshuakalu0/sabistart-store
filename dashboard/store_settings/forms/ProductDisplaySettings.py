import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import ProductDisplaySettings

logger = logging.getLogger(__name__)


class ProductDisplaySettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Product Display Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = ProductDisplaySettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === PRODUCT CARD STYLE ===
            'card_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # === GRID LAYOUT ===
            'products_per_row_desktop': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'products_per_row_tablet': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'products_per_row_mobile': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'products_per_page': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 12,
                'max': 100
            }),

            # === PRODUCT INFORMATION ===
            'show_product_vendor': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_product_sku': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_product_rating': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_review_count': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_short_description': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'short_description_length': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 50,
                'max': 200
            }),

            # === BADGES & LABELS ===
            'show_sale_badge': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_new_badge': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'new_badge_days': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 90
            }),
            'show_stock_status': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_discount_percentage': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === PRICING ===
            'price_display': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_tax_label': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === IMAGES ===
            'image_ratio': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'image_hover_effect': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_multiple_images': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === ACTIONS ===
            'show_add_to_cart_button': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'add_to_cart_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_quick_view': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_wishlist_button': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_compare_button': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === SORTING & FILTERING ===
            'default_sort_order': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_filters_sidebar': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'filters_position': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # === PAGINATION ===
            'pagination_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
        }

    def clean_products_per_page(self):
        """Validate products per page range."""
        per_page = self.cleaned_data.get('products_per_page')
        if per_page and not (12 <= per_page <= 100):
            raise ValidationError(
                _("Products per page must be between 12 and 100."))
        return per_page

    def clean_short_description_length(self):
        """Validate short description length range."""
        length = self.cleaned_data.get('short_description_length')
        if length and not (50 <= length <= 200):
            raise ValidationError(
                _("Short description length must be between 50 and 200 characters."))
        return length

    def clean_new_badge_days(self):
        """Validate new badge days range."""
        days = self.cleaned_data.get('new_badge_days')
        if days and not (1 <= days <= 90):
            raise ValidationError(
                _("New badge days must be between 1 and 90."))
        return days

    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()

        # If short description is disabled, length setting is irrelevant
        show_desc = cleaned_data.get('show_short_description')
        desc_length = cleaned_data.get('short_description_length')
        if not show_desc:
            logger.info(
                "Short description disabled - length setting will be ignored")

        # If multiple images is disabled, hover effect may be limited
        show_multi = cleaned_data.get('show_multiple_images')
        hover_effect = cleaned_data.get('image_hover_effect')
        if not show_multi and hover_effect in ['fade', 'slide']:
            logger.warning(
                "Multiple images disabled but fade/slide hover effect selected")

        # If add to cart button is disabled, style setting is irrelevant
        show_cart = cleaned_data.get('show_add_to_cart_button')
        cart_style = cleaned_data.get('add_to_cart_style')
        if not show_cart:
            logger.info(
                "Add to cart button disabled - style setting will be ignored")

        # If filters sidebar is disabled, position setting is irrelevant
        show_filters = cleaned_data.get('show_filters_sidebar')
        filters_pos = cleaned_data.get('filters_position')
        if not show_filters:
            logger.info(
                "Filters sidebar disabled - position setting will be ignored")

        # Validate grid layout consistency (desktop >= tablet >= mobile)
        desktop = cleaned_data.get('products_per_row_desktop')
        tablet = cleaned_data.get('products_per_row_tablet')
        mobile = cleaned_data.get('products_per_row_mobile')

        if desktop and tablet and desktop < tablet:
            logger.warning(
                "Desktop products per row is less than tablet - may cause layout issues")

        if tablet and mobile and tablet < mobile:
            logger.warning(
                "Tablet products per row is less than mobile - may cause layout issues")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"ProductDisplaySettings saved (tenant schema: {instance._meta.db_table})"
        )
        return instance
