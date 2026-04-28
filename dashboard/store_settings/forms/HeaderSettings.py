import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import HeaderSettings

logger = logging.getLogger(__name__)


class HeaderSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Header Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = HeaderSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === HEADER LAYOUT ===
            'layout': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'is_sticky': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'is_transparent': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'background_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'text_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'height': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 60,
                'max': 150
            }),

            # === LOGO ===
            'logo_max_width': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 80,
                'max': 400
            }),
            'logo_position': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # === ANNOUNCEMENT BAR ===
            'show_announcement_bar': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'announcement_text': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Free shipping on orders over $50!'
            }),
            'announcement_background_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'announcement_text_color': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'color',
                'style': 'height: 40px; padding: 2px;'
            }),
            'announcement_link': forms.URLInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'https://...'
            }),

            # === NAVIGATION ===
            'nav_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_categories_in_nav': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'max_nav_items': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 3,
                'max': 12
            }),

            # === SEARCH ===
            'show_search': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'search_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'search_placeholder': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Search products...'
            }),

            # === CART & ACCOUNT ===
            'show_cart_icon': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cart_icon_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'show_cart_count': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'cart_preview_on_hover': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_account_icon': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'show_wishlist_icon': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === MOBILE MENU ===
            'mobile_menu_style': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
        }

    def clean_height(self):
        """Validate header height range."""
        height = self.cleaned_data.get('height')
        if height and not (60 <= height <= 150):
            raise ValidationError(
                _("Header height must be between 60 and 150 pixels."))
        return height

    def clean_logo_max_width(self):
        """Validate logo max width range."""
        width = self.cleaned_data.get('logo_max_width')
        if width and not (80 <= width <= 400):
            raise ValidationError(
                _("Logo max width must be between 80 and 400 pixels."))
        return width

    def clean_max_nav_items(self):
        """Validate max nav items range."""
        items = self.cleaned_data.get('max_nav_items')
        if items and not (3 <= items <= 12):
            raise ValidationError(_("Max nav items must be between 3 and 12."))
        return items

    def clean_background_color(self):
        """Validate background color hex format."""
        color = self.cleaned_data.get('background_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #FFFFFF)."))
        return color

    def clean_text_color(self):
        """Validate text color hex format."""
        color = self.cleaned_data.get('text_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #000000)."))
        return color

    def clean_announcement_background_color(self):
        """Validate announcement background color hex format."""
        color = self.cleaned_data.get('announcement_background_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #000000)."))
        return color

    def clean_announcement_text_color(self):
        """Validate announcement text color hex format."""
        color = self.cleaned_data.get('announcement_text_color')
        if color and not color.startswith('#'):
            raise ValidationError(
                _("Color must be in hex format (e.g., #FFFFFF)."))
        return color

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === Announcement Bar Logic ===
        show_announcement = cleaned_data.get('show_announcement_bar')
        announcement_text = cleaned_data.get('announcement_text')

        if show_announcement and not announcement_text:
            self.add_error(
                'announcement_text',
                _("Announcement text is required when announcement bar is enabled.")
            )

        # === Search Logic ===
        show_search = cleaned_data.get('show_search')
        search_placeholder = cleaned_data.get('search_placeholder')

        if show_search and not search_placeholder:
            self.add_error(
                'search_placeholder',
                _("Search placeholder is required when search is enabled.")
            )

        # === Cart Icon Logic ===
        show_cart = cleaned_data.get('show_cart_icon')
        show_cart_count = cleaned_data.get('show_cart_count')
        cart_preview = cleaned_data.get('cart_preview_on_hover')

        if not show_cart:
            logger.info(
                "Cart icon disabled - cart count and preview settings will be ignored")

        # === Transparent Header Warning ===
        is_transparent = cleaned_data.get('is_transparent')
        background_color = cleaned_data.get('background_color')

        if is_transparent and background_color and background_color != '#FFFFFF':
            logger.warning(
                "Transparent header enabled but custom background color set - may cause visibility issues")

        # === Logo Position vs Layout ===
        layout = cleaned_data.get('layout')
        logo_position = cleaned_data.get('logo_position')

        if layout == 'centered' and logo_position != 'center':
            logger.info(
                "Centered layout selected but logo position is not center - logo will be centered automatically")

        if layout == 'sidebar' and logo_position != 'left':
            logger.info(
                "Sidebar layout selected - logo position will be forced to left")

        # === Nav Style vs Layout ===
        nav_style = cleaned_data.get('nav_style')

        if layout == 'sidebar' and nav_style != 'sidebar':
            logger.info(
                "Sidebar layout selected - nav style will be forced to sidebar drawer")

        # === Color Contrast Warning ===
        bg_color = cleaned_data.get('background_color')
        txt_color = cleaned_data.get('text_color')

        if bg_color and txt_color and bg_color == txt_color:
            self.add_error(
                'text_color',
                _("Text color and background color are the same - this will cause visibility issues.")
            )

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"HeaderSettings saved: {instance.layout} (ID: {instance.id})"
        )
        return instance
