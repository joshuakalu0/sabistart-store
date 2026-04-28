from django.contrib import admin
from .models import (
    Store, POSProduct, StoreInventory, InventoryAdjustment,
    POSTransaction, POSTransactionItem, POSPayment, POSDiscount
)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'manager', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(POSProduct)
class POSProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'barcode', 'selling_price', 'is_active']
    list_filter = ['is_active', 'product_type', 'category']
    search_fields = ['name', 'sku', 'barcode']


@admin.register(StoreInventory)
class StoreInventoryAdmin(admin.ModelAdmin):
    list_display = ['store', 'product', 'quantity', 'low_stock_threshold']
    list_filter = ['store']
    search_fields = ['product__name', 'product__sku']


@admin.register(POSTransaction)
class POSTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_number', 'store', 'cashier', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'transaction_type']
    search_fields = ['transaction_number', 'customer_name']
    readonly_fields = ['created_at', 'updated_at']


admin.site.register(InventoryAdjustment)
admin.site.register(POSTransactionItem)
admin.site.register(POSPayment)
admin.site.register(POSDiscount)