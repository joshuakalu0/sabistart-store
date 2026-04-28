from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class PopupSettings(models.Model):
    """
    Marketing popups and promotional banners configuration.
    
    CONTROLS:
    - Newsletter popups
    - Exit intent popups
    - Promotional banners
    - Cookie consent
    - Announcement bars
    
    IMPACT:
    - Lead generation
    - Marketing campaigns
    - Compliance (GDPR, cookies)
    """
    
    # === NEWSLETTER POPUP ===
    enable_newsletter_popup = models.BooleanField(
        default=False,
        help_text="Enable newsletter signup popup"
    )
    
    popup_title = models.CharField(
        max_length=100,
        default='Join Our Newsletter',
        help_text="Popup headline"
    )
    
    popup_description = models.TextField(
        max_length=300,
        default='Subscribe to get special offers, free giveaways, and exclusive deals.',
        help_text="Popup description text"
    )
    
    popup_image = models.ImageField(
        upload_to='popups/',
        blank=True,
        null=True,
        help_text="Popup background or side image"
    )
    
    popup_button_text = models.CharField(
        max_length=50,
        default='Subscribe'
    )
    
    show_discount_code = models.BooleanField(
        default=False,
        help_text="Offer discount code for subscribing"
    )
    
    discount_code_text = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., 'Get 10% off your first order!'"
    )
    
    # === TRIGGER SETTINGS ===
    trigger_type = models.CharField(
        max_length=20,
        choices=[
            ('time', 'Time Delay'),
            ('scroll', 'Scroll Percentage'),
            ('exit', 'Exit Intent'),
            ('immediate', 'Immediate'),
            ('click', 'On Click'),
        ],
        default='time',
        help_text="When to show popup"
    )
    
    trigger_delay_seconds = models.IntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(60)],
        help_text="Delay before showing popup (seconds)"
    )
    
    trigger_scroll_percentage = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Scroll percentage to trigger popup"
    )
    
    # === FREQUENCY ===
    show_once_per_session = models.BooleanField(
        default=False,
        help_text="Show only once per browser session"
    )
    
    show_once_per_days = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Don't show again for X days after closing"
    )
    
    show_to_subscribers = models.BooleanField(
        default=False,
        help_text="Show popup to existing subscribers"
    )
    
    show_on_mobile = models.BooleanField(
        default=True,
        help_text="Show popup on mobile devices"
    )
    
    # === APPEARANCE ===
    popup_position = models.CharField(
        max_length=20,
        choices=[
            ('center', 'Center'),
            ('bottom_right', 'Bottom Right'),
            ('bottom_left', 'Bottom Left'),
            ('bottom_center', 'Bottom Center'),
            ('top', 'Top Bar'),
            ('fullscreen', 'Fullscreen'),
        ],
        default='center'
    )
    
    popup_size = models.CharField(
        max_length=20,
        choices=[
            ('small', 'Small'),
            ('medium', 'Medium'),
            ('large', 'Large'),
        ],
        default='medium'
    )
    
    overlay_opacity = models.IntegerField(
        default=70,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Background overlay opacity (0-100%)"
    )
    
    popup_animation = models.CharField(
        max_length=20,
        choices=[
            ('fade', 'Fade In'),
            ('slide_up', 'Slide Up'),
            ('slide_down', 'Slide Down'),
            ('zoom', 'Zoom In'),
            ('none', 'No Animation'),
        ],
        default='fade'
    )
    
    enable_close_button = models.BooleanField(
        default=True,
        help_text="Show close (X) button"
    )
    
    close_on_overlay_click = models.BooleanField(
        default=True,
        help_text="Close popup when clicking outside"
    )
    
    # === COOKIE CONSENT ===
    enable_cookie_consent = models.BooleanField(
        default=True,
        help_text="Show cookie consent banner (GDPR compliance)"
    )
    
    cookie_message = models.TextField(
        max_length=300,
        default='We use cookies to improve your experience on our site. By using our site, you consent to cookies.',
        help_text="Cookie consent message"
    )
    
    cookie_button_text = models.CharField(
        max_length=50,
        default='Accept'
    )
    
    cookie_policy_url = models.URLField(
        blank=True,
        help_text="Link to cookie policy page"
    )
    
    cookie_banner_position = models.CharField(
        max_length=20,
        choices=[
            ('top', 'Top'),
            ('bottom', 'Bottom'),
            ('popup', 'Center Popup'),
        ],
        default='bottom'
    )
    
    show_cookie_settings = models.BooleanField(
        default=True,
        help_text="Allow users to customize cookie preferences"
    )
    
    # === PROMOTIONAL BANNER ===
    enable_promo_banner = models.BooleanField(
        default=False,
        help_text="Show promotional announcement banner"
    )
    
    promo_banner_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Banner text (e.g., 'Free shipping on orders over $50!')"
    )
    
    promo_banner_link = models.URLField(
        blank=True,
        help_text="Optional link when clicking banner"
    )
    
    promo_banner_background = models.CharField(
        max_length=7,
        default='#000000',
        help_text="Banner background color"
    )
    
    promo_banner_text_color = models.CharField(
        max_length=7,
        default='#FFFFFF',
        help_text="Banner text color"
    )
    
    promo_banner_position = models.CharField(
        max_length=10,
        choices=[('top', 'Top'), ('bottom', 'Bottom')],
        default='top'
    )
    
    promo_banner_dismissible = models.BooleanField(
        default=True,
        help_text="Allow users to close banner"
    )
    
    promo_banner_sticky = models.BooleanField(
        default=True,
        help_text="Keep banner visible when scrolling"
    )
    
    # === EXIT INTENT ===
    enable_exit_intent = models.BooleanField(
        default=False,
        help_text="Show popup when user attempts to leave"
    )
    
    exit_intent_title = models.CharField(
        max_length=100,
        default='Wait! Before you go...',
        blank=True
    )
    
    exit_intent_message = models.TextField(
        max_length=300,
        blank=True,
        help_text="Exit intent popup message"
    )
    
    exit_intent_offer = models.CharField(
        max_length=100,
        blank=True,
        help_text="Special offer (e.g., '10% off your first order')"
    )
    
    # === A/B TESTING ===
    enable_ab_testing = models.BooleanField(
        default=False,
        help_text="Enable A/B testing for popups"
    )
    
    variant_a_title = models.CharField(max_length=100, blank=True)
    variant_b_title = models.CharField(max_length=100, blank=True)
    
    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'popup_settings'
        verbose_name = 'Popup Setting'
        verbose_name_plural = 'Popup Settings'
    
    def __str__(self):
        return "Popup Settings"


