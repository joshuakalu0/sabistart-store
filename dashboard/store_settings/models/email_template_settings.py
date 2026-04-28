from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class EmailTemplateSettings(models.Model):
    """
    Customize transactional email appearance.

    CONTROLS:
    - Email header/footer
    - Colors and branding
    - Social links in emails

    EMAIL TYPES:
    - Order confirmation
    - Shipping notification
    - Password reset
    - Welcome email
    - Abandoned cart

    IMPACT:
    - Customer communication
    - Brand consistency

    SHOPIFY EQUIVALENT: Settings > Notifications > Email templates
    """

    # === BRANDING ===
    logo = models.ImageField(
        upload_to='emails/logos/',
        blank=True,
        null=True,
        help_text="Logo for email header (recommended: 200x60px)"
    )

    accent_color = models.CharField(
        max_length=7,
        default='#2563EB',
        help_text="Button and link color"
    )

    background_color = models.CharField(
        max_length=7,
        default='#F3F4F6',
        help_text="Email background color"
    )

    content_background_color = models.CharField(
        max_length=7,
        default='#FFFFFF',
        help_text="Content area background"
    )

    text_color = models.CharField(
        max_length=7,
        default='#1F2937'
    )

    # === HEADER ===
    header_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Text above logo (optional)"
    )

    show_social_links_in_header = models.BooleanField(default=False)

    # === FOOTER ===
    footer_text = models.TextField(
        blank=True,
        max_length=500,
        help_text="Footer message (supports HTML)"
    )

    show_contact_info = models.BooleanField(
        default=True,
        help_text="Show store contact info in footer"
    )

    show_social_links_in_footer = models.BooleanField(default=True)

    show_unsubscribe_link = models.BooleanField(
        default=True,
        help_text="Show unsubscribe link (required for marketing emails)"
    )

    # === CONTENT ===
    BUTTON_STYLE_CHOICES = [
        ('solid', 'Solid Button'),
        ('outline', 'Outline Button'),
        ('link', 'Text Link'),
    ]

    button_style = models.CharField(
        max_length=20,
        choices=BUTTON_STYLE_CHOICES,
        default='solid'
    )

    button_border_radius = models.IntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(50)]
    )

    # === TYPOGRAPHY ===
    FONT_CHOICES = [
        ('system', 'System Default'),
        ('arial', 'Arial'),
        ('helvetica', 'Helvetica'),
        ('georgia', 'Georgia'),
        ('times', 'Times New Roman'),
    ]

    font_family = models.CharField(
        max_length=20,
        choices=FONT_CHOICES,
        default='system'
    )

    # === SPECIFIC EMAIL SETTINGS ===
    order_confirmation_custom_message = models.TextField(
        blank=True,
        max_length=300,
        help_text="Additional message in order confirmation emails"
    )

    shipping_notification_custom_message = models.TextField(
        blank=True,
        max_length=300,
        help_text="Additional message in shipping notification emails"
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'email_template_settings'
        verbose_name = 'Email Template Setting'
        verbose_name_plural = 'Email Template Settings'

    def __str__(self):
        return "Email Template Settings"

    def get_font_stack(self):
        """Get CSS font stack based on choice"""
        font_stacks = {
            'system': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            'arial': 'Arial, sans-serif',
            'helvetica': 'Helvetica, Arial, sans-serif',
            'georgia': 'Georgia, serif',
            'times': '"Times New Roman", Times, serif',
        }
        return font_stacks.get(self.font_family, font_stacks['system'])


