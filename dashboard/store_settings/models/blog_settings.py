from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class BlogSettings(models.Model):
    """
    Blog and content marketing settings.
    
    CONTROLS:
    - Blog layout and display
    - Post settings
    - Comments and engagement
    - SEO for blog posts
    
    IMPACT:
    - Content marketing
    - SEO performance
    - Customer engagement
    
    SHOPIFY EQUIVALENT: Online Store > Blog posts
    """
    
    # === GENERAL ===
    enable_blog = models.BooleanField(
        default=True,
        help_text="Enable blog functionality"
    )
    
    blog_title = models.CharField(
        max_length=100,
        default='Blog',
        help_text="Blog section title"
    )
    
    blog_description = models.TextField(
        max_length=300,
        blank=True,
        help_text="Blog description for SEO"
    )
    
    blog_url_prefix = models.SlugField(
        max_length=50,
        default='blog',
        help_text="URL prefix for blog (e.g., /blog/)"
    )
    
    # === LAYOUT ===
    layout = models.CharField(
        max_length=20,
        choices=[
            ('grid', 'Grid Layout'),
            ('list', 'List Layout'),
            ('masonry', 'Masonry Grid'),
            ('magazine', 'Magazine Style'),
            ('cards', 'Card Style'),
        ],
        default='grid'
    )
    
    posts_per_page = models.IntegerField(
        default=12,
        validators=[MinValueValidator(6), MaxValueValidator(50)],
        help_text="Blog posts per page"
    )
    
    posts_per_row = models.IntegerField(
        default=3,
        choices=[(1, '1 Column'), (2, '2 Columns'), (3, '3 Columns'), (4, '4 Columns')],
        help_text="Posts per row in grid layout"
    )
    
    show_sidebar = models.BooleanField(
        default=True,
        help_text="Show sidebar on blog pages"
    )
    
    sidebar_position = models.CharField(
        max_length=10,
        choices=[('left', 'Left'), ('right', 'Right')],
        default='right'
    )
    
    # === POST DISPLAY ===
    show_featured_image = models.BooleanField(
        default=True,
        help_text="Show featured image on post listings"
    )
    
    featured_image_aspect_ratio = models.CharField(
        max_length=20,
        choices=[
            ('16_9', '16:9 (Landscape)'),
            ('4_3', '4:3'),
            ('1_1', '1:1 (Square)'),
            ('auto', 'Original'),
        ],
        default='16_9'
    )
    
    show_author = models.BooleanField(
        default=True,
        help_text="Show post author"
    )
    
    show_author_avatar = models.BooleanField(
        default=True,
        help_text="Show author profile picture"
    )
    
    show_date = models.BooleanField(
        default=True,
        help_text="Show publish date"
    )
    
    date_format = models.CharField(
        max_length=20,
        choices=[
            ('relative', 'Relative (2 days ago)'),
            ('short', 'Short (Jan 15, 2024)'),
            ('long', 'Long (January 15, 2024)'),
        ],
        default='short'
    )
    
    show_reading_time = models.BooleanField(
        default=True,
        help_text="Show estimated reading time"
    )
    
    show_excerpt = models.BooleanField(
        default=True,
        help_text="Show post excerpt/summary"
    )
    
    excerpt_length = models.IntegerField(
        default=150,
        validators=[MinValueValidator(50), MaxValueValidator(500)],
        help_text="Maximum excerpt length in characters"
    )
    
    show_read_more_button = models.BooleanField(
        default=True,
        help_text="Show 'Read More' button"
    )
    
    show_tags = models.BooleanField(
        default=True,
        help_text="Show post tags"
    )
    
    show_categories = models.BooleanField(
        default=True,
        help_text="Show post categories"
    )
    
    show_view_count = models.BooleanField(
        default=False,
        help_text="Show post view count"
    )
    
    # === SINGLE POST ===
    show_author_bio = models.BooleanField(
        default=True,
        help_text="Show author bio on single post"
    )
    
    show_share_buttons = models.BooleanField(
        default=True,
        help_text="Show social sharing buttons"
    )
    
    share_button_position = models.CharField(
        max_length=20,
        choices=[
            ('top', 'Top of Post'),
            ('bottom', 'Bottom of Post'),
            ('both', 'Top and Bottom'),
            ('floating', 'Floating Sidebar'),
        ],
        default='both'
    )
    
    show_related_posts = models.BooleanField(
        default=True,
        help_text="Show related posts"
    )
    
    related_posts_count = models.IntegerField(
        default=3,
        validators=[MinValueValidator(2), MaxValueValidator(12)]
    )
    
    show_post_navigation = models.BooleanField(
        default=True,
        help_text="Show previous/next post links"
    )
    
    # === COMMENTS ===
    enable_comments = models.BooleanField(
        default=True,
        help_text="Enable comments on blog posts"
    )
    
    comment_system = models.CharField(
        max_length=20,
        choices=[
            ('native', 'Native Comments'),
            ('disqus', 'Disqus'),
            ('facebook', 'Facebook Comments'),
            ('commento', 'Commento'),
            ('disabled', 'Disabled'),
        ],
        default='native'
    )
    
    require_approval = models.BooleanField(
        default=True,
        help_text="Require admin approval for comments"
    )
    
    require_login_to_comment = models.BooleanField(
        default=False,
        help_text="Require login to post comments"
    )
    
    show_comment_count = models.BooleanField(
        default=True,
        help_text="Show comment count on post listings"
    )
    
    # === SEO ===
    auto_generate_meta = models.BooleanField(
        default=True,
        help_text="Auto-generate meta descriptions from excerpt"
    )
    
    show_breadcrumbs = models.BooleanField(
        default=True,
        help_text="Show breadcrumb navigation"
    )
    
    enable_schema_markup = models.BooleanField(
        default=True,
        help_text="Add structured data (schema.org) markup"
    )
    
    # === SIDEBAR WIDGETS ===
    show_search_widget = models.BooleanField(default=True)
    show_categories_widget = models.BooleanField(default=True)
    show_recent_posts_widget = models.BooleanField(default=True)
    show_popular_posts_widget = models.BooleanField(default=True)
    show_tags_widget = models.BooleanField(default=True)
    show_newsletter_widget = models.BooleanField(default=True)
    
    recent_posts_count = models.IntegerField(default=5)
    popular_posts_count = models.IntegerField(default=5)
    
    # === RSS FEED ===
    enable_rss_feed = models.BooleanField(
        default=True,
        help_text="Enable RSS feed"
    )
    
    rss_posts_count = models.IntegerField(
        default=20,
        validators=[MinValueValidator(5), MaxValueValidator(100)],
        help_text="Number of posts in RSS feed"
    )
    
    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'blog_settings'
        verbose_name = 'Blog Setting'
        verbose_name_plural = 'Blog Settings'
    
    def __str__(self):
        return f"Blog Settings: {self.blog_title}"



