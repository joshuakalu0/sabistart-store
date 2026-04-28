from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class SearchSettings(models.Model):
    """
    Search functionality and results display configuration.
    
    CONTROLS:
    - Search behavior and autocomplete
    - Search scope (products, pages, blog)
    - Results display and filtering
    - Search suggestions
    
    IMPACT:
    - Product discoverability
    - User experience
    - Conversion rate
    
    SHOPIFY EQUIVALENT: Theme > Search
    """
    
    # === SEARCH BEHAVIOR ===
    enable_autocomplete = models.BooleanField(
        default=True,
        help_text="Show search suggestions as user types"
    )
    
    autocomplete_delay = models.IntegerField(
        default=300,
        validators=[MinValueValidator(100), MaxValueValidator(2000)],
        help_text="Delay before showing suggestions (milliseconds)"
    )
    
    min_characters = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Minimum characters before triggering search"
    )
    
    max_suggestions = models.IntegerField(
        default=8,
        validators=[MinValueValidator(3), MaxValueValidator(20)],
        help_text="Maximum number of autocomplete suggestions"
    )
    
    # === SEARCH SCOPE ===
    search_products = models.BooleanField(
        default=True,
        help_text="Include products in search"
    )
    
    search_product_title = models.BooleanField(
        default=True,
        help_text="Search in product titles"
    )
    
    search_product_description = models.BooleanField(
        default=True,
        help_text="Search in product descriptions"
    )
    
    search_product_sku = models.BooleanField(
        default=True,
        help_text="Search by product SKU"
    )
    
    search_product_tags = models.BooleanField(
        default=True,
        help_text="Search in product tags"
    )
    
    search_categories = models.BooleanField(
        default=True,
        help_text="Include categories in search"
    )
    
    search_pages = models.BooleanField(
        default=True,
        help_text="Include custom pages in search"
    )
    
    search_blog_posts = models.BooleanField(
        default=False,
        help_text="Include blog posts in search"
    )
    
    search_vendors = models.BooleanField(
        default=False,
        help_text="Search by vendor/brand name"
    )
    
    # === AUTOCOMPLETE DISPLAY ===
    show_product_images = models.BooleanField(
        default=True,
        help_text="Show product images in autocomplete"
    )
    
    show_product_prices = models.BooleanField(
        default=True,
        help_text="Show prices in autocomplete"
    )
    
    show_product_ratings = models.BooleanField(
        default=False,
        help_text="Show ratings in autocomplete"
    )
    
    show_stock_status = models.BooleanField(
        default=True,
        help_text="Show stock status in autocomplete"
    )
    
    show_category_suggestions = models.BooleanField(
        default=True,
        help_text="Show matching categories"
    )
    
    show_popular_searches = models.BooleanField(
        default=True,
        help_text="Show popular/trending searches"
    )
    
    popular_searches_count = models.IntegerField(
        default=5,
        validators=[MinValueValidator(3), MaxValueValidator(10)]
    )
    
    # === SEARCH RESULTS PAGE ===
    results_per_page = models.IntegerField(
        default=24,
        validators=[MinValueValidator(12), MaxValueValidator(100)],
        help_text="Products per page in search results"
    )
    
    results_layout = models.CharField(
        max_length=20,
        choices=[
            ('grid', 'Grid Layout'),
            ('list', 'List Layout'),
            ('mixed', 'Mixed Layout'),
        ],
        default='grid'
    )
    
    show_filters = models.BooleanField(
        default=True,
        help_text="Show filter sidebar on results page"
    )
    
    show_sort_options = models.BooleanField(
        default=True,
        help_text="Show sort dropdown"
    )
    
    show_search_term = models.BooleanField(
        default=True,
        help_text="Display search query at top of results"
    )
    
    show_result_count = models.BooleanField(
        default=True,
        help_text="Show number of results found"
    )
    
    show_search_time = models.BooleanField(
        default=False,
        help_text="Show search execution time"
    )
    
    # === SEARCH ALGORITHM ===
    enable_fuzzy_search = models.BooleanField(
        default=True,
        help_text="Tolerate typos and misspellings"
    )
    
    fuzzy_threshold = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Maximum character differences for fuzzy matching"
    )
    
    enable_synonym_search = models.BooleanField(
        default=False,
        help_text="Search for synonyms (e.g., 'phone' finds 'mobile')"
    )
    
    enable_partial_match = models.BooleanField(
        default=True,
        help_text="Match partial words (e.g., 'run' finds 'running')"
    )
    
    search_ranking = models.CharField(
        max_length=20,
        choices=[
            ('relevance', 'Relevance'),
            ('popularity', 'Popularity'),
            ('newest', 'Newest First'),
            ('price_asc', 'Price: Low to High'),
            ('price_desc', 'Price: High to Low'),
        ],
        default='relevance',
        help_text="Default search result ranking"
    )
    
    # === NO RESULTS ===
    no_results_message = models.CharField(
        max_length=200,
        default='No products found for "{query}"',
        help_text="Message when no results (use {query} placeholder)"
    )
    
    show_suggestions_on_no_results = models.BooleanField(
        default=True,
        help_text="Show 'Did you mean...' suggestions"
    )
    
    show_popular_products_on_no_results = models.BooleanField(
        default=True,
        help_text="Show popular products when no results"
    )
    
    popular_products_title = models.CharField(
        max_length=100,
        default='Popular Products'
    )
    
    popular_products_count = models.IntegerField(
        default=8,
        validators=[MinValueValidator(4), MaxValueValidator(20)]
    )
    
    show_all_categories_on_no_results = models.BooleanField(
        default=False,
        help_text="Show category list when no results"
    )
    
    # === SEARCH ANALYTICS ===
    track_search_queries = models.BooleanField(
        default=True,
        help_text="Track search queries for analytics"
    )
    
    track_no_results_queries = models.BooleanField(
        default=True,
        help_text="Track queries that returned no results"
    )
    
    track_click_through = models.BooleanField(
        default=True,
        help_text="Track which results users click"
    )
    
    # === ADVANCED ===
    enable_voice_search = models.BooleanField(
        default=False,
        help_text="Enable voice search input"
    )
    
    enable_barcode_search = models.BooleanField(
        default=False,
        help_text="Enable barcode/QR code search"
    )
    
    enable_image_search = models.BooleanField(
        default=False,
        help_text="Enable visual/image search"
    )
    
    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'search_settings'
        verbose_name = 'Search Setting'
        verbose_name_plural = 'Search Settings'
    
    def __str__(self):
        return "Search Settings"
    
    def clean(self):
        errors = {}
        
        if not any([self.search_products, self.search_categories, 
                   self.search_pages, self.search_blog_posts]):
            errors['search_products'] = "At least one search scope must be enabled."
        
        if errors:
            raise ValidationError(errors)



