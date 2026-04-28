from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class SocialMediaLinks(models.Model):
    """
    Store social media profile links.

    CONTROLS:
    - Social platform URLs
    - Display preferences

    PLATFORMS:
    - Facebook, Instagram, Twitter/X
    - Pinterest, TikTok, YouTube
    - LinkedIn, WhatsApp

    IMPACT:
    - Footer social icons
    - Product sharing
    - Social proof

    SHOPIFY EQUIVALENT: Theme settings > Social media
    """

    # === SOCIAL LINKS ===
    facebook_url = models.URLField(
        blank=True,
        help_text="Full URL (e.g., https://facebook.com/yourstore)"
    )

    instagram_url = models.URLField(blank=True)

    twitter_url = models.URLField(
        blank=True,
        help_text="Twitter/X profile URL"
    )

    pinterest_url = models.URLField(blank=True)

    tiktok_url = models.URLField(blank=True)

    youtube_url = models.URLField(blank=True)

    linkedin_url = models.URLField(blank=True)

    snapchat_url = models.URLField(blank=True)

    whatsapp_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="WhatsApp number with country code (e.g., +1234567890)"
    )

    # === DISPLAY SETTINGS ===
    icon_style = models.CharField(
        max_length=20,
        choices=[
            ('filled', 'Filled Icons'),
            ('outline', 'Outline Icons'),
            ('colored', 'Brand Colors'),
            ('mono', 'Monochrome'),
        ],
        default='filled'
    )

    icon_size = models.CharField(
        max_length=20,
        choices=[
            ('small', 'Small'),
            ('medium', 'Medium'),
            ('large', 'Large'),
        ],
        default='medium'
    )

    # === SHARING ===
    enable_product_sharing = models.BooleanField(
        default=True,
        help_text="Show share buttons on product pages"
    )

    sharing_platforms = models.JSONField(
        default=list,
        blank=True,
        help_text="Platforms for sharing: ['facebook', 'twitter', 'pinterest', 'whatsapp']"
    )

    # === INSTAGRAM INTEGRATION ===
    instagram_access_token = models.CharField(
        max_length=500,
        blank=True,
        help_text="Instagram API token for feed display"
    )

    show_instagram_feed = models.BooleanField(
        default=False,
        help_text="Display Instagram feed on site"
    )

    instagram_feed_count = models.IntegerField(
        default=6,
        validators=[MinValueValidator(4), MaxValueValidator(12)],
        help_text="Number of Instagram photos to show"
    )

    # === FACEBOOK INTEGRATION ===
    facebook_app_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="For Facebook sharing and analytics"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'social_media_links'
        verbose_name = 'Social Media Links'
        verbose_name_plural = 'Social Media Links'

    def __str__(self):
        return "Social Media Links"

    def get_active_platforms(self):
        """Return list of platforms with configured URLs"""
        platforms = []
        if self.facebook_url:
            platforms.append(('facebook', self.facebook_url))
        if self.instagram_url:
            platforms.append(('instagram', self.instagram_url))
        if self.twitter_url:
            platforms.append(('twitter', self.twitter_url))
        if self.pinterest_url:
            platforms.append(('pinterest', self.pinterest_url))
        if self.tiktok_url:
            platforms.append(('tiktok', self.tiktok_url))
        if self.youtube_url:
            platforms.append(('youtube', self.youtube_url))
        if self.linkedin_url:
            platforms.append(('linkedin', self.linkedin_url))
        return platforms


