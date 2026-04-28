import logging
import json
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import HomepageLayout

logger = logging.getLogger(__name__)


class HomepageLayoutForm(forms.ModelForm):
    """
    Comprehensive form for managing Homepage Layout.
    Organized into logical sections for better UX.
    """

    # JSON Field for section order - using a text area for simplicity
    section_order = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 font-mono shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
            'rows': 4,
            'placeholder': "['hero', 'categories', 'featured', 'new_arrivals', 'best_sellers', 'sale', 'promo_banners', 'testimonials', 'blog', 'instagram']"
        }),
        help_text="Comma-separated list of section names in order"
    )

    class Meta:
        model = HomepageLayout
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === HERO SECTION ===
            'show_hero': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'hero_type': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'hero_height': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'hero_autoplay': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'hero_autoplay_speed': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 2000,
                'max': 10000
            }),

            # === FEATURED CATEGORIES ===
            'show_featured_categories': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'featured_categories_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Shop by Category'
            }),
            'featured_categories_layout': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'featured_categories_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 3,
                'max': 12
            }),

            # === FEATURED PRODUCTS ===
            'show_featured_products': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'featured_products_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Featured Products'
            }),
            'featured_products_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 4,
                'max': 20
            }),

            # === NEW ARRIVALS ===
            'show_new_arrivals': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'new_arrivals_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'New Arrivals'
            }),
            'new_arrivals_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 4,
                'max': 20
            }),
            'new_arrivals_days': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 7,
                'max': 90
            }),

            # === BEST SELLERS ===
            'show_best_sellers': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'best_sellers_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Best Sellers'
            }),
            'best_sellers_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 4,
                'max': 20
            }),

            # === SALE SECTION ===
            'show_sale_section': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'sale_section_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'On Sale'
            }),
            'sale_section_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 4,
                'max': 20
            }),

            # === PROMOTIONAL BANNERS ===
            'show_promo_banners': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'promo_banner_layout': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),

            # === TESTIMONIALS ===
            'show_testimonials': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'testimonials_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'What Our Customers Say'
            }),
            'testimonials_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 2,
                'max': 10
            }),

            # === BLOG POSTS ===
            'show_blog_posts': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'blog_posts_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Latest from Our Blog'
            }),
            'blog_posts_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 2,
                'max': 6
            }),

            # === INSTAGRAM FEED ===
            'show_instagram_feed': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'instagram_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Follow Us on Instagram'
            }),
            'instagram_handle': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'yourstore'
            }),

            # === BRANDS/PARTNERS ===
            'show_brands': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'brands_title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Featured Brands'
            }),
        }

    def clean_hero_autoplay_speed(self):
        """Validate hero autoplay speed range."""
        speed = self.cleaned_data.get('hero_autoplay_speed')
        if speed and not (2000 <= speed <= 10000):
            raise ValidationError(_("Hero autoplay speed must be between 2000 and 10000 milliseconds."))
        return speed

    def clean_featured_categories_count(self):
        """Validate featured categories count range."""
        count = self.cleaned_data.get('featured_categories_count')
        if count and not (3 <= count <= 12):
            raise ValidationError(_("Featured categories count must be between 3 and 12."))
        return count

    def clean_featured_products_count(self):
        """Validate featured products count range."""
        count = self.cleaned_data.get('featured_products_count')
        if count and not (4 <= count <= 20):
            raise ValidationError(_("Featured products count must be between 4 and 20."))
        return count

    def clean_new_arrivals_count(self):
        """Validate new arrivals count range."""
        count = self.cleaned_data.get('new_arrivals_count')
        if count and not (4 <= count <= 20):
            raise ValidationError(_("New arrivals count must be between 4 and 20."))
        return count

    def clean_new_arrivals_days(self):
        """Validate new arrivals days range."""
        days = self.cleaned_data.get('new_arrivals_days')
        if days and not (7 <= days <= 90):
            raise ValidationError(_("New arrivals days must be between 7 and 90."))
        return days

    def clean_best_sellers_count(self):
        """Validate best sellers count range."""
        count = self.cleaned_data.get('best_sellers_count')
        if count and not (4 <= count <= 20):
            raise ValidationError(_("Best sellers count must be between 4 and 20."))
        return count

    def clean_sale_section_count(self):
        """Validate sale section count range."""
        count = self.cleaned_data.get('sale_section_count')
        if count and not (4 <= count <= 20):
            raise ValidationError(_("Sale section count must be between 4 and 20."))
        return count

    def clean_testimonials_count(self):
        """Validate testimonials count range."""
        count = self.cleaned_data.get('testimonials_count')
        if count and not (2 <= count <= 10):
            raise ValidationError(_("Testimonials count must be between 2 and 10."))
        return count

    def clean_blog_posts_count(self):
        """Validate blog posts count range."""
        count = self.cleaned_data.get('blog_posts_count')
        if count and not (2 <= count <= 6):
            raise ValidationError(_("Blog posts count must be between 2 and 6."))
        return count

    def clean_section_order(self):
        """Validate and convert section order from comma-separated string to list."""
        order_str = self.cleaned_data.get('section_order', '')

        if not order_str:
            # Return default order if empty
            return ['hero', 'categories', 'featured', 'new_arrivals', 'best_sellers', 'promo_banners', 'sale', 'testimonials', 'blog', 'instagram']

        # Parse comma-separated string
        sections = [section.strip().lower() for section in order_str.split(',') if section.strip()]

        # Validate section names
        valid_sections = ['hero', 'categories', 'featured', 'new_arrivals', 'best_sellers', 'promo_banners', 'sale', 'testimonials', 'blog', 'instagram', 'brands']
        invalid_sections = [s for s in sections if s not in valid_sections]

        if invalid_sections:
            raise ValidationError(_("Invalid section names: %(sections)s. Valid sections are: %(valid)s") % {
                'sections': ', '.join(invalid_sections),
                'valid': ', '.join(valid_sections)
            })

        return sections

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === Hero Section Logic ===
        show_hero = cleaned_data.get('show_hero')
        hero_type = cleaned_data.get('hero_type')
        autoplay_speed = cleaned_data.get('hero_autoplay_speed')

        if show_hero and hero_type == 'slider' and not autoplay_speed:
            self.add_error(
                'hero_autoplay_speed',
                _("Autoplay speed is required when hero slider is enabled.")
            )

        # === Featured Categories Logic ===
        show_categories = cleaned_data.get('show_featured_categories')
        categories_count = cleaned_data.get('featured_categories_count')

        if show_categories and not categories_count:
            self.add_error(
                'featured_categories_count',
                _("Featured categories count is required when section is enabled.")
            )

        # === Product Sections Logic ===
        product_sections = [
            ('show_featured_products', 'featured_products_count'),
            ('show_new_arrivals', 'new_arrivals_count'),
            ('show_best_sellers', 'best_sellers_count'),
            ('show_sale_section', 'sale_section_count'),
        ]

        for show_field, count_field in product_sections:
            if cleaned_data.get(show_field) and not cleaned_data.get(count_field):
                self.add_error(
                    count_field,
                    _("%(section)s count is required when section is enabled.") % {
                        'section': show_field.replace('show_', '').replace('_', ' ').title()
                    }
                )

        # === Instagram Feed Logic ===
        show_instagram = cleaned_data.get('show_instagram_feed')
        instagram_handle = cleaned_data.get('instagram_handle')

        if show_instagram and not instagram_handle:
            self.add_error(
                'instagram_handle',
                _("Instagram handle is required when Instagram feed is enabled.")
            )

        # === Section Order Validation ===
        section_order = cleaned_data.get('section_order')
        show_hero = cleaned_data.get('show_hero')

        # If hero is shown but not in section order, add warning
        if show_hero and 'hero' not in section_order:
            logger.warning("Hero section is enabled but not included in section order")

        # Check for duplicate sections in order
        if section_order and len(section_order) != len(set(section_order)):
            self.add_error(
                'section_order',
                _("Section order contains duplicate sections.")
            )

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"HomepageLayout saved (ID: {instance.id})"
        )
        return instance