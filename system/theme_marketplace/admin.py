from django.contrib import admin

from system.theme_marketplace.models import Theme, ThemeBasePage, ThemeCategory


@admin.register(ThemeCategory)
class ThemeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    search_fields = ("name", "slug")


class ThemeBasePageInline(admin.TabularInline):
    model = ThemeBasePage
    extra = 0


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "status", "is_published", "is_featured", "price", "downloads")
    list_filter = ("status", "is_published", "is_featured", "category")
    search_fields = ("name", "slug", "description")
    inlines = [ThemeBasePageInline]
