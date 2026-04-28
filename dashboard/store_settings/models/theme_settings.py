import logging
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

logger = logging.getLogger(__name__)


class ThemeSettings(models.Model):
    """
    Core visual theme for the entire storefront.

    CONTROLS:
    - Brand colors (primary, secondary, accent)
    - Typography (fonts, sizes)
    - Spacing and layout
    - Border radius and shadows
    - Button styles

    IMPACT:
    - Affects entire site appearance
    - One theme per tenant
    - Changes apply site-wide instantly

    SHOPIFY EQUIVALENT: Theme customization > Colors & Typography
    """

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    theme_name = models.CharField(max_length=100, default="Default Theme")

    # === COLOR SCHEME ===
    # Primary brand color (main buttons, links, accents)
    primary_color = models.CharField(
        max_length=7,
        default="#2563EB",
        help_text="Main brand color (hex format: #RRGGBB)"
    )

    # Secondary color (hover states, secondary buttons)
    secondary_color = models.CharField(
        max_length=7,
        default="#1E40AF",
        help_text="Secondary brand color"
    )

    # Accent color (badges, notifications, highlights)
    accent_color = models.CharField(
        max_length=7,
        default="#F59E0B",
        help_text="Accent color for highlights"
    )

    # Background colors
    background_color = models.CharField(
        max_length=7,
        default="#FFFFFF",
        help_text="Main background color"
    )

    secondary_background_color = models.CharField(
        max_length=7,
        default="#F9FAFB",
        help_text="Alternate background (sections, cards)"
    )

    # Text colors
    text_color = models.CharField(
        max_length=7,
        default="#111827",
        help_text="Main text color"
    )

    secondary_text_color = models.CharField(
        max_length=7,
        default="#6B7280",
        help_text="Secondary text (descriptions, meta)"
    )

    # Border and divider colors
    border_color = models.CharField(
        max_length=7,
        default="#E5E7EB",
        help_text="Border and divider color"
    )

    # Success, warning, error colors
    success_color = models.CharField(max_length=7, default="#10B981")
    warning_color = models.CharField(max_length=7, default="#F59E0B")
    error_color = models.CharField(max_length=7, default="#EF4444")

    # === TYPOGRAPHY ===
    # Font families
    FONT_CHOICES = [
        ('system', 'System Default'),
        ('inter', 'Inter'),
        ('roboto', 'Roboto'),
        ('open-sans', 'Open Sans'),
        ('lato', 'Lato'),
        ('montserrat', 'Montserrat'),
        ('poppins', 'Poppins'),
        ('playfair', 'Playfair Display'),
        ('merriweather', 'Merriweather'),
        ('custom', 'Custom Font'),
    ]

    heading_font = models.CharField(
        max_length=50,
        choices=FONT_CHOICES,
        default='inter',
        help_text="Font for headings (H1-H6)"
    )

    body_font = models.CharField(
        max_length=50,
        choices=FONT_CHOICES,
        default='inter',
        help_text="Font for body text"
    )

    custom_font_url = models.URLField(
        blank=True,
        help_text="Google Fonts URL or custom font URL"
    )

    # Font sizes (in rem units)
    base_font_size = models.IntegerField(
        default=16,
        validators=[MinValueValidator(12), MaxValueValidator(20)],
        help_text="Base font size in pixels"
    )

    heading_size_multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=1.5,
        validators=[MinValueValidator(1.0), MaxValueValidator(3.0)],
        help_text="H1 size multiplier (relative to base)"
    )

    # Font weights
    heading_font_weight = models.IntegerField(
        default=700,
        choices=[(300, 'Light'), (400, 'Regular'), (500, 'Medium'),
                 (600, 'Semi-Bold'), (700, 'Bold'), (800, 'Extra Bold')],
        help_text="Font weight for headings"
    )

    body_font_weight = models.IntegerField(
        default=400,
        choices=[(300, 'Light'), (400, 'Regular'), (500, 'Medium'),
                 (600, 'Semi-Bold')],
        help_text="Font weight for body text"
    )

    # === LAYOUT & SPACING ===
    container_width = models.IntegerField(
        default=1200,
        validators=[MinValueValidator(960), MaxValueValidator(1920)],
        help_text="Max content width in pixels"
    )

    SPACING_CHOICES = [
        ('compact', 'Compact'),
        ('normal', 'Normal'),
        ('relaxed', 'Relaxed'),
        ('spacious', 'Spacious'),
    ]

    spacing_scale = models.CharField(
        max_length=20,
        choices=SPACING_CHOICES,
        default='normal',
        help_text="Overall spacing between elements"
    )

    # === BORDERS & SHADOWS ===
    border_radius = models.IntegerField(
        default=8,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Corner radius in pixels (0 = sharp, 50 = very round)"
    )

    use_shadows = models.BooleanField(
        default=True,
        help_text="Enable drop shadows on cards and elements"
    )

    shadow_intensity = models.CharField(
        max_length=20,
        choices=[
            ('none', 'None'),
            ('subtle', 'Subtle'),
            ('medium', 'Medium'),
            ('strong', 'Strong'),
        ],
        default='medium'
    )

    # === BUTTONS ===
    BUTTON_STYLE_CHOICES = [
        ('solid', 'Solid Fill'),
        ('outline', 'Outline'),
        ('ghost', 'Ghost'),
        ('gradient', 'Gradient'),
    ]

    primary_button_style = models.CharField(
        max_length=20,
        choices=BUTTON_STYLE_CHOICES,
        default='solid'
    )

    button_border_radius = models.IntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Button corner radius"
    )

    button_text_transform = models.CharField(
        max_length=20,
        choices=[
            ('none', 'Normal'),
            ('uppercase', 'UPPERCASE'),
            ('lowercase', 'lowercase'),
            ('capitalize', 'Capitalize'),
        ],
        default='none'
    )

    class Meta:
        db_table = 'theme_settings'
        verbose_name = 'Theme Setting'
        verbose_name_plural = 'Theme Settings'
        indexes = [
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"Theme: {self.theme_name}"

    def generate_css_variables(self):
        """Generate CSS custom properties from theme settings"""
        return f"""
        :root {{
            /* Colors */
            --color-primary: {self.primary_color};
            --color-secondary: {self.secondary_color};
            --color-accent: {self.accent_color};
            --color-background: {self.background_color};
            --color-background-secondary: {self.secondary_background_color};
            --color-text: {self.text_color};
            --color-text-secondary: {self.secondary_text_color};
            --color-border: {self.border_color};
            --color-success: {self.success_color};
            --color-warning: {self.warning_color};
            --color-error: {self.error_color};

            /* Typography */
            --font-heading: {self.get_font_family(self.heading_font)};
            --font-body: {self.get_font_family(self.body_font)};
            --font-size-base: {self.base_font_size}px;
            --font-weight-heading: {self.heading_font_weight};
            --font-weight-body: {self.body_font_weight};

            /* Layout */
            --container-width: {self.container_width}px;
            --spacing-unit: {self.get_spacing_unit()}px;
            --border-radius: {self.border_radius}px;
            --button-radius: {self.button_border_radius}px;

            /* Shadows */
            --shadow: {self.get_shadow_value()};
        }}
        """

    def get_font_family(self, font_choice):
        """Convert font choice to CSS font-family value"""
        font_map = {
            'system': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            'inter': '"Inter", sans-serif',
            'roboto': '"Roboto", sans-serif',
            'open-sans': '"Open Sans", sans-serif',
            'lato': '"Lato", sans-serif',
            'montserrat': '"Montserrat", sans-serif',
            'poppins': '"Poppins", sans-serif',
            'playfair': '"Playfair Display", serif',
            'merriweather': '"Merriweather", serif',
        }
        return font_map.get(font_choice, font_map['system'])

    def get_spacing_unit(self):
        """Get base spacing unit based on scale"""
        spacing_map = {
            'compact': 4,
            'normal': 8,
            'relaxed': 12,
            'spacious': 16,
        }
        return spacing_map.get(self.spacing_scale, 8)

    def get_shadow_value(self):
        """Get CSS box-shadow value based on intensity"""
        shadows = {
            'none': 'none',
            'subtle': '0 1px 3px rgba(0, 0, 0, 0.1)',
            'medium': '0 4px 6px rgba(0, 0, 0, 0.1)',
            'strong': '0 10px 15px rgba(0, 0, 0, 0.15)',
        }
        return shadows.get(self.shadow_intensity, shadows['medium'])
