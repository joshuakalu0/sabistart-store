import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ShopTheme(models.Model):
    """Theme installed in a shop - tenant specific"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop_id = models.CharField(max_length=100, db_index=True)
    theme_id = models.UUIDField(db_index=True)  # Reference to shared Theme
    
    # Installation details
    folder_path = models.CharField(max_length=500)
    is_active = models.BooleanField(default=False, db_index=True)
    
    # Customization tracking
    is_customized = models.BooleanField(default=False)
    last_customized = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    installed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'shop_themes'
        verbose_name = _('Shop Theme')
        verbose_name_plural = _('Shop Themes')
        unique_together = ['shop_id', 'theme_id']
        indexes = [
            models.Index(fields=['shop_id', 'is_active']),
        ]
    
    def __str__(self):
        return f"Shop {self.shop_id} - Theme {self.theme_id}"

    @property
    def theme(self):
        from system.theme_marketplace.models import Theme

        return Theme.objects.filter(pk=self.theme_id).first()

    @property
    def theme_name(self):
        theme = self.theme
        return theme.name if theme else str(self.theme_id)


class ShopThemePage(models.Model):
    """Customizable pages in shop's theme - tenant specific"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop_theme = models.ForeignKey(ShopTheme, on_delete=models.CASCADE, related_name='pages')
    
    page_name = models.CharField(max_length=100, db_index=True)
    file_path = models.CharField(max_length=500)
    css_path = models.CharField(max_length=500, blank=True)
    
    # Customization tracking
    is_customized = models.BooleanField(default=False)
    original_content_hash = models.CharField(max_length=64, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'shop_theme_pages'
        verbose_name = _('Shop Theme Page')
        verbose_name_plural = _('Shop Theme Pages')
        unique_together = ['shop_theme', 'page_name']
    
    def __str__(self):
        return f"{self.shop_theme} - {self.page_name}"
