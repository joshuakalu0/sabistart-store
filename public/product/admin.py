from django.contrib import admin

from .models import (
    Product, ProductImage, ProductVideo,
    ProductAttributeValue, Attribute, AttributeValue,
    ProductVariant, Category, Tag, Brand,
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "product_type", "status", "is_active", "is_pos_available")
    list_filter = ("product_type", "status", "is_active", "is_pos_available")
    search_fields = ("name", "sku", "slug")


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "variant_name", "sku", "is_active", "is_pos_available")
    list_filter = ("is_active", "is_pos_available")
    search_fields = ("product__name", "variant_name", "sku", "barcode")


admin.site.register(ProductImage)
admin.site.register(ProductVideo)
admin.site.register(ProductAttributeValue)
admin.site.register(Attribute)
admin.site.register(AttributeValue)
