import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import SearchSettings

logger = logging.getLogger(__name__)


class SearchSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Search Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = SearchSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === SEARCH BEHAVIOR ===
            'enable_autocomplete': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'autocomplete_delay': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 100,
                'max': 2000,
                'step': 100
            }),
            'min_characters': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 5
            }),
            'max_suggestions': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 3,
                'max': 20
            }),

            # === SEARCH SCOPE ===
            'search_products': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_product_title': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_product_description': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_product_sku': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_product_tags': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_categories': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_pages': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_blog_posts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_vendors': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === AUTOCOMPLETE DISPLAY ===
            'show_product_images': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_product_prices': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_product_ratings': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_stock_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_category_suggestions': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_popular_searches': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'popular_searches_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 3,
                'max': 10
            }),

            # === SEARCH RESULTS PAGE ===
            'results_per_page': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 12,
                'max': 100
            }),
            'results_layout': forms.Select(attrs={'class': 'form-select'}),
            'show_filters': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_sort_options': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_search_term': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_result_count': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_search_time': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === SEARCH ALGORITHM ===
            'enable_fuzzy_search': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'fuzzy_threshold': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 5
            }),
            'enable_synonym_search': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_partial_match': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'search_ranking': forms.Select(attrs={'class': 'form-select'}),

            # === NO RESULTS ===
            'no_results_message': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'No products found for "{query}"'
            }),
            'show_suggestions_on_no_results': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_popular_products_on_no_results': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'popular_products_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Popular Products'
            }),
            'popular_products_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 4,
                'max': 20
            }),
            'show_all_categories_on_no_results': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === SEARCH ANALYTICS ===
            'track_search_queries': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'track_no_results_queries': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'track_click_through': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === ADVANCED ===
            'enable_voice_search': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_barcode_search': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_image_search': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_autocomplete_delay(self):
        """Validate autocomplete delay range."""
        delay = self.cleaned_data.get('autocomplete_delay')
        if delay and not (100 <= delay <= 2000):
            raise ValidationError(
                _("Autocomplete delay must be between 100 and 2000 milliseconds."))
        return delay

    def clean_min_characters(self):
        """Validate minimum characters range."""
        chars = self.cleaned_data.get('min_characters')
        if chars and not (1 <= chars <= 5):
            raise ValidationError(
                _("Minimum characters must be between 1 and 5."))
        return chars

    def clean_max_suggestions(self):
        """Validate max suggestions range."""
        max_sug = self.cleaned_data.get('max_suggestions')
        if max_sug and not (3 <= max_sug <= 20):
            raise ValidationError(
                _("Maximum suggestions must be between 3 and 20."))
        return max_sug

    def clean_fuzzy_threshold(self):
        """Validate fuzzy threshold range."""
        threshold = self.cleaned_data.get('fuzzy_threshold')
        if threshold and not (1 <= threshold <= 5):
            raise ValidationError(
                _("Fuzzy threshold must be between 1 and 5."))
        return threshold

    def clean_results_per_page(self):
        """Validate results per page range."""
        per_page = self.cleaned_data.get('results_per_page')
        if per_page and not (12 <= per_page <= 100):
            raise ValidationError(
                _("Results per page must be between 12 and 100."))
        return per_page

    def clean_popular_searches_count(self):
        """Validate popular searches count range."""
        count = self.cleaned_data.get('popular_searches_count')
        if count and not (3 <= count <= 10):
            raise ValidationError(
                _("Popular searches count must be between 3 and 10."))
        return count

    def clean_popular_products_count(self):
        """Validate popular products count range."""
        count = self.cleaned_data.get('popular_products_count')
        if count and not (4 <= count <= 20):
            raise ValidationError(
                _("Popular products count must be between 4 and 20."))
        return count

    def clean_no_results_message(self):
        """Validate no results message contains placeholder."""
        message = self.cleaned_data.get('no_results_message')
        if message and '{query}' not in message:
            logger.warning(
                "no_results_message does not contain {query} placeholder")
        return message

    def clean(self):
        """Cross-field validation for search scope."""
        cleaned_data = super().clean()

        # At least one search scope must be enabled
        scope_fields = [
            'search_products',
            'search_categories',
            'search_pages',
            'search_blog_posts',
        ]

        enabled_scopes = [
            field for field in scope_fields
            if cleaned_data.get(field, False)
        ]

        if not enabled_scopes:
            raise ValidationError(
                _("At least one search scope must be enabled (Products, Categories, Pages, or Blog Posts).")
            )

        # If fuzzy search is disabled, fuzzy_threshold should be ignored
        if not cleaned_data.get('enable_fuzzy_search'):
            logger.info(
                "Fuzzy search disabled - threshold setting will be ignored")

        # If synonym search is enabled, recommend tracking search queries
        if cleaned_data.get('enable_synonym_search') and not cleaned_data.get('track_search_queries'):
            logger.warning(
                "Synonym search enabled but query tracking is disabled")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"SearchSettings saved (tenant schema: {instance._meta.db_table})"
        )
        return instance
