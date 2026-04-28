import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import BlogSettings

logger = logging.getLogger(__name__)


class BlogSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Blog Settings.
    Organized into logical sections for better UX.
    """

    class Meta:
        model = BlogSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === GENERAL ===
            'enable_blog': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'blog_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Blog'
            }),
            'blog_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Blog description for SEO...',
                'maxlength': 300
            }),
            'blog_url_prefix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'blog'
            }),

            # === LAYOUT ===
            'layout': forms.Select(attrs={'class': 'form-select'}),
            'posts_per_page': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 6,
                'max': 50
            }),
            'posts_per_row': forms.Select(attrs={'class': 'form-select'}),
            'show_sidebar': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sidebar_position': forms.Select(attrs={'class': 'form-select'}),

            # === POST DISPLAY ===
            'show_featured_image': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'featured_image_aspect_ratio': forms.Select(attrs={'class': 'form-select'}),
            'show_author': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_author_avatar': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_date': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'date_format': forms.Select(attrs={'class': 'form-select'}),
            'show_reading_time': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_excerpt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'excerpt_length': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 50,
                'max': 500
            }),
            'show_read_more_button': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_tags': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_categories': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_view_count': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === SINGLE POST ===
            'show_author_bio': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_share_buttons': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'share_button_position': forms.Select(attrs={'class': 'form-select'}),
            'show_related_posts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'related_posts_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 2,
                'max': 12
            }),
            'show_post_navigation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === COMMENTS ===
            'enable_comments': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'comment_system': forms.Select(attrs={'class': 'form-select'}),
            'require_approval': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'require_login_to_comment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_comment_count': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === SEO ===
            'auto_generate_meta': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_breadcrumbs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_schema_markup': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === SIDEBAR WIDGETS ===
            'show_search_widget': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_categories_widget': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_recent_posts_widget': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_popular_posts_widget': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_tags_widget': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_newsletter_widget': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'recent_posts_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 20
            }),
            'popular_posts_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 20
            }),

            # === RSS FEED ===
            'enable_rss_feed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'rss_posts_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 5,
                'max': 100
            }),
        }

    def clean_posts_per_page(self):
        """Validate posts per page range."""
        count = self.cleaned_data.get('posts_per_page')
        if count and not (6 <= count <= 50):
            raise ValidationError(
                _("Posts per page must be between 6 and 50."))
        return count

    def clean_excerpt_length(self):
        """Validate excerpt length range."""
        length = self.cleaned_data.get('excerpt_length')
        if length and not (50 <= length <= 500):
            raise ValidationError(
                _("Excerpt length must be between 50 and 500 characters."))
        return length

    def clean_related_posts_count(self):
        """Validate related posts count range."""
        count = self.cleaned_data.get('related_posts_count')
        if count and not (2 <= count <= 12):
            raise ValidationError(
                _("Related posts count must be between 2 and 12."))
        return count

    def clean_recent_posts_count(self):
        """Validate recent posts count range."""
        count = self.cleaned_data.get('recent_posts_count')
        if count and count < 1:
            raise ValidationError(_("Recent posts count must be at least 1."))
        return count

    def clean_popular_posts_count(self):
        """Validate popular posts count range."""
        count = self.cleaned_data.get('popular_posts_count')
        if count and count < 1:
            raise ValidationError(_("Popular posts count must be at least 1."))
        return count

    def clean_rss_posts_count(self):
        """Validate RSS posts count range."""
        count = self.cleaned_data.get('rss_posts_count')
        if count and not (5 <= count <= 100):
            raise ValidationError(
                _("RSS posts count must be between 5 and 100."))
        return count

    def clean_blog_url_prefix(self):
        """Validate blog URL prefix."""
        prefix = self.cleaned_data.get('blog_url_prefix')
        if prefix:
            # Check for valid slug format
            import re
            if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', prefix):
                raise ValidationError(
                    _("URL prefix must be a valid slug (lowercase letters, numbers, and hyphens only)."))
        return prefix

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === Blog Enabled Logic ===
        enable_blog = cleaned_data.get('enable_blog')

        if not enable_blog:
            logger.warning(
                "Blog functionality is disabled - all blog settings will be ignored")

        # === Sidebar Logic ===
        show_sidebar = cleaned_data.get('show_sidebar')
        sidebar_position = cleaned_data.get('sidebar_position')

        if sidebar_position and not show_sidebar:
            logger.info("Sidebar position is set but sidebar is disabled")

        # === Author Display Logic ===
        show_author = cleaned_data.get('show_author')
        show_author_avatar = cleaned_data.get('show_author_avatar')
        show_author_bio = cleaned_data.get('show_author_bio')

        if show_author_avatar and not show_author:
            logger.warning(
                "Author avatar is enabled but author display is disabled")

        if show_author_bio and not show_author:
            logger.warning(
                "Author bio is enabled but author display is disabled")

        # === Date Display Logic ===
        show_date = cleaned_data.get('show_date')
        date_format = cleaned_data.get('date_format')

        if date_format and not show_date:
            logger.info("Date format is set but date display is disabled")

        # === Excerpt Logic ===
        show_excerpt = cleaned_data.get('show_excerpt')
        excerpt_length = cleaned_data.get('excerpt_length')

        if show_excerpt and not excerpt_length:
            self.add_error(
                'excerpt_length',
                _("Excerpt length is required when excerpt display is enabled.")
            )

        # === Comments Logic ===
        enable_comments = cleaned_data.get('enable_comments')
        comment_system = cleaned_data.get('comment_system')
        require_approval = cleaned_data.get('require_approval')
        require_login = cleaned_data.get('require_login_to_comment')
        show_comment_count = cleaned_data.get('show_comment_count')

        if enable_comments and comment_system == 'disabled':
            self.add_error(
                'comment_system',
                _("Comment system cannot be disabled when comments are enabled.")
            )

        if require_login and comment_system == 'facebook':
            logger.info(
                "Facebook comments require Facebook login - require_login setting may be redundant")

        if show_comment_count and not enable_comments:
            logger.warning(
                "Comment count is enabled but comments are disabled")

        # === Share Buttons Logic ===
        show_share = cleaned_data.get('show_share_buttons')
        share_position = cleaned_data.get('share_button_position')

        if share_position and not show_share:
            logger.info(
                "Share button position is set but share buttons are disabled")

        # === Related Posts Logic ===
        show_related = cleaned_data.get('show_related_posts')
        related_count = cleaned_data.get('related_posts_count')

        if show_related and not related_count:
            self.add_error(
                'related_posts_count',
                _("Related posts count is required when related posts are enabled.")
            )

        # === Sidebar Widgets Logic ===
        show_sidebar = cleaned_data.get('show_sidebar')
        widget_fields = [
            'show_search_widget',
            'show_categories_widget',
            'show_recent_posts_widget',
            'show_popular_posts_widget',
            'show_tags_widget',
            'show_newsletter_widget',
        ]

        widgets_enabled = sum([cleaned_data.get(field, False)
                              for field in widget_fields])

        if show_sidebar and widgets_enabled == 0:
            logger.warning("Sidebar is enabled but no widgets are selected")

        # === RSS Feed Logic ===
        enable_rss = cleaned_data.get('enable_rss_feed')
        rss_count = cleaned_data.get('rss_posts_count')

        if enable_rss and not rss_count:
            self.add_error(
                'rss_posts_count',
                _("RSS posts count is required when RSS feed is enabled.")
            )

        # === SEO Optimization Warnings ===
        if not cleaned_data.get('auto_generate_meta'):
            logger.warning(
                "Auto-generate meta is disabled - manual meta descriptions required for SEO")

        if not cleaned_data.get('enable_schema_markup'):
            logger.info(
                "Schema markup disabled - may impact search engine rich snippets")

        if not cleaned_data.get('show_breadcrumbs'):
            logger.info(
                "Breadcrumbs disabled - may impact user navigation and SEO")

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"BlogSettings saved: {instance.blog_title} (enabled: {instance.enable_blog}, layout: {instance.layout})"
        )
        return instance
