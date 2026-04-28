import logging
import json
import re
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import SocialMediaLinks

logger = logging.getLogger(__name__)


class SocialMediaLinksForm(forms.ModelForm):
    """
    Comprehensive form for managing Social Media Links.
    Includes URL validation and platform selection widgets.
    """

    # Multi-select widget for sharing platforms
    sharing_platforms = forms.MultipleChoiceField(
        choices=[
            ('facebook', 'Facebook'),
            ('twitter', 'Twitter/X'),
            ('instagram', 'Instagram'),
            ('pinterest', 'Pinterest'),
            ('whatsapp', 'WhatsApp'),
            ('linkedin', 'LinkedIn'),
            ('tiktok', 'TikTok'),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'flex flex-col gap-2'
        }),
        help_text="Select platforms for product sharing buttons"
    )

    class Meta:
        model = SocialMediaLinks
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === SOCIAL LINKS ===
            'facebook_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://facebook.com/yourstore'
            }),
            'instagram_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://instagram.com/yourstore'
            }),
            'twitter_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://twitter.com/yourstore'
            }),
            'pinterest_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://pinterest.com/yourstore'
            }),
            'tiktok_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://tiktok.com/@yourstore'
            }),
            'youtube_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://youtube.com/@yourstore'
            }),
            'linkedin_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://linkedin.com/company/yourstore'
            }),
            'snapchat_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://snapchat.com/add/yourstore'
            }),
            'whatsapp_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1234567890'
            }),

            # === DISPLAY SETTINGS ===
            'icon_style': forms.Select(attrs={'class': 'form-select'}),
            'icon_size': forms.Select(attrs={'class': 'form-select'}),

            # === TOGGLES ===
            'enable_product_sharing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_instagram_feed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # === INTEGRATION ===
            'instagram_access_token': forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'IGQVJ...'
            }),
            'facebook_app_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '1234567890'
            }),
            'instagram_feed_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 4,
                'max': 12
            }),
        }

    def clean_facebook_url(self):
        """Validate Facebook URL format."""
        url = self.cleaned_data.get('facebook_url')
        if url:
            if 'facebook.com' not in url and 'fb.com' not in url:
                raise ValidationError(_("Please enter a valid Facebook URL."))
        return url

    def clean_instagram_url(self):
        """Validate Instagram URL format."""
        url = self.cleaned_data.get('instagram_url')
        if url:
            if 'instagram.com' not in url:
                raise ValidationError(_("Please enter a valid Instagram URL."))
        return url

    def clean_twitter_url(self):
        """Validate Twitter/X URL format."""
        url = self.cleaned_data.get('twitter_url')
        if url:
            if 'twitter.com' not in url and 'x.com' not in url:
                raise ValidationError(_("Please enter a valid Twitter/X URL."))
        return url

    def clean_pinterest_url(self):
        """Validate Pinterest URL format."""
        url = self.cleaned_data.get('pinterest_url')
        if url:
            if 'pinterest.com' not in url:
                raise ValidationError(_("Please enter a valid Pinterest URL."))
        return url

    def clean_tiktok_url(self):
        """Validate TikTok URL format."""
        url = self.cleaned_data.get('tiktok_url')
        if url:
            if 'tiktok.com' not in url:
                raise ValidationError(_("Please enter a valid TikTok URL."))
        return url

    def clean_youtube_url(self):
        """Validate YouTube URL format."""
        url = self.cleaned_data.get('youtube_url')
        if url:
            if 'youtube.com' not in url and 'youtu.be' not in url:
                raise ValidationError(_("Please enter a valid YouTube URL."))
        return url

    def clean_linkedin_url(self):
        """Validate LinkedIn URL format."""
        url = self.cleaned_data.get('linkedin_url')
        if url:
            if 'linkedin.com' not in url:
                raise ValidationError(_("Please enter a valid LinkedIn URL."))
        return url

    def clean_whatsapp_number(self):
        """Validate WhatsApp number format."""
        number = self.cleaned_data.get('whatsapp_number')
        if number:
            # Remove spaces, dashes, parentheses
            cleaned = re.sub(r'[\s\-\(\)]', '', number)
            # Must start with + and have at least 10 digits
            if not cleaned.startswith('+') or len(re.sub(r'[^\d]', '', cleaned)) < 10:
                raise ValidationError(
                    _("WhatsApp number must include country code (e.g., +1234567890).")
                )
            return cleaned
        return number

    def clean_instagram_access_token(self):
        """Validate Instagram access token format."""
        token = self.cleaned_data.get('instagram_access_token')
        if token:
            # Basic validation - tokens are typically long alphanumeric strings
            if len(token) < 50:
                logger.warning("Instagram access token seems unusually short.")
        return token

    def clean_facebook_app_id(self):
        """Validate Facebook App ID format."""
        app_id = self.cleaned_data.get('facebook_app_id')
        if app_id:
            if not app_id.isdigit():
                raise ValidationError(_("Facebook App ID must be numeric."))
        return app_id

    def clean_instagram_feed_count(self):
        """Validate Instagram feed count."""
        count = self.cleaned_data.get('instagram_feed_count')
        if count and not (4 <= count <= 12):
            raise ValidationError(_("Feed count must be between 4 and 12."))
        return count

    def clean_sharing_platforms(self):
        """Convert multiple choice to JSON-serializable list."""
        platforms = self.cleaned_data.get('sharing_platforms', [])
        return platforms

    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()

        # If Instagram feed is enabled, access token should be provided
        show_feed = cleaned_data.get('show_instagram_feed')
        access_token = cleaned_data.get('instagram_access_token')

        if show_feed and not access_token:
            self.add_error(
                'instagram_access_token',
                _("Instagram access token is required to show the feed.")
            )

        # If product sharing is enabled, at least one platform should be selected
        enable_sharing = cleaned_data.get('enable_product_sharing')
        platforms = cleaned_data.get('sharing_platforms')

        if enable_sharing and not platforms:
            self.add_error(
                'sharing_platforms',
                _("Select at least one platform for product sharing.")
            )

        return cleaned_data

    def save(self, commit=True):
        """Save and convert sharing_platforms to JSON."""
        instance = super().save(commit=False)

        # Convert list to JSON for the JSONField
        instance.sharing_platforms = self.cleaned_data.get(
            'sharing_platforms', [])

        if commit:
            instance.save()
            logger.info(
                f"SocialMediaLinks saved (tenant: {instance._meta.db_table})"
            )

        return instance
