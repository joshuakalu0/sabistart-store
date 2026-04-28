from django.db import models


class FooterSettings(models.Model):
    """
    Customize footer appearance and content.

    CONTROLS:
    - Footer layout and columns
    - Copyright text
    - Payment method icons
    - Newsletter signup
    - Social media links display

    IMPACT:
    - Bottom of every page
    - Trust signals and legal info

    SHOPIFY EQUIVALENT: Theme > Footer
    """

    # === LAYOUT ===
    LAYOUT_CHOICES = [
        ('4_columns', '4 Columns'),
        ('3_columns', '3 Columns'),
        ('2_columns', '2 Columns'),
        ('minimal', 'Minimal (Single Column)'),
    ]

    layout = models.CharField(
        max_length=20,
        choices=LAYOUT_CHOICES,
        default='4_columns'
    )

    background_color = models.CharField(
        max_length=7,
        default='#1F2937'
    )

    text_color = models.CharField(
        max_length=7,
        default='#FFFFFF'
    )

    # === CONTENT ===
    show_logo = models.BooleanField(
        default=True,
        help_text="Show store logo in footer"
    )

    about_text = models.TextField(
        blank=True,
        max_length=300,
        help_text="Short about text (e.g., 'Quality products since 2020')"
    )

    copyright_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g., '© 2024 YourStore. All rights reserved.'"
    )

    # === NEWSLETTER ===
    show_newsletter = models.BooleanField(
        default=True,
        help_text="Show newsletter signup in footer"
    )

    newsletter_title = models.CharField(
        max_length=100,
        default='Subscribe to our newsletter'
    )

    newsletter_description = models.CharField(
        max_length=200,
        default='Get the latest updates on new products and upcoming sales'
    )

    # === PAYMENT METHODS ===
    show_payment_icons = models.BooleanField(
        default=True,
        help_text="Show accepted payment method icons"
    )

    accepted_payments = models.JSONField(
        default=list,
        blank=True,
        help_text="List of payment methods: ['visa', 'mastercard', 'paypal', etc.]"
    )

    # === SOCIAL MEDIA ===
    show_social_links = models.BooleanField(default=True)

    social_links_style = models.CharField(
        max_length=20,
        choices=[
            ('icons', 'Icon Only'),
            ('text', 'Text Links'),
            ('both', 'Icons with Text'),
        ],
        default='icons'
    )

    # === TRUST BADGES ===
    show_trust_badges = models.BooleanField(
        default=False,
        help_text="Show security/trust badges (SSL, verified, etc.)"
    )

    trust_badge_1 = models.ImageField(
        upload_to='footer/badges/',
        blank=True,
        null=True
    )

    trust_badge_2 = models.ImageField(
        upload_to='footer/badges/',
        blank=True,
        null=True
    )

    trust_badge_3 = models.ImageField(
        upload_to='footer/badges/',
        blank=True,
        null=True
    )

    # === LEGAL LINKS ===
    show_legal_links = models.BooleanField(
        default=True,
        help_text="Show Terms, Privacy Policy, etc."
    )

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'footer_settings'
        verbose_name = 'Footer Setting'
        verbose_name_plural = 'Footer Settings'

    def __str__(self):
        return f"Footer Settings ({self.layout})"
