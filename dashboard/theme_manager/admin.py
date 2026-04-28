# from django.contrib import admin
# from django.utils.html import format_html
# from django.urls import reverse
# from django.utils.safestring import mark_safe
# from .models import Theme, ThemeBasePage, ShopTheme, ShopThemePage, ThemeReview, ThemeCategory


# @admin.register(Theme)
# class ThemeAdmin(admin.ModelAdmin):
#     list_display = ['name', 'creator', 'version', 'status', 'is_published', 'price', 'downloads', 'rating', 'created_at']
#     list_filter = ['status', 'is_published', 'is_featured', 'is_free', 'created_at']
#     search_fields = ['name', 'description', 'creator__username']
#     readonly_fields = ['slug', 'downloads', 'rating', 'created_at', 'updated_at']

#     fieldsets = (
#         ('Basic Information', {
#             'fields': ('name', 'slug', 'creator', 'description', 'version')
#         }),
#         ('Pricing', {
#             'fields': ('price', 'is_free')
#         }),
#         ('Files', {
#             'fields': ('zip_file', 'thumbnail', 'folder_path')
#         }),
#         ('Status', {
#             'fields': ('status', 'is_published', 'is_featured')
#         }),
#         ('Statistics', {
#             'fields': ('downloads', 'rating'),
#             'classes': ('collapse',)
#         }),
#         ('Metadata', {
#             'fields': ('tags', 'requirements'),
#             'classes': ('collapse',)
#         }),
#         ('Timestamps', {
#             'fields': ('created_at', 'updated_at', 'published_at'),
#             'classes': ('collapse',)
#         }),
#     )

#     actions = ['approve_themes', 'reject_themes', 'publish_themes']

#     def approve_themes(self, request, queryset):
#         queryset.update(status='approved')
#         self.message_user(request, f'{queryset.count()} themes approved.')
#     approve_themes.short_description = "Approve selected themes"

#     def reject_themes(self, request, queryset):
#         queryset.update(status='rejected')
#         self.message_user(request, f'{queryset.count()} themes rejected.')
#     reject_themes.short_description = "Reject selected themes"

#     def publish_themes(self, request, queryset):
#         queryset.update(is_published=True)
#         self.message_user(request, f'{queryset.count()} themes published.')
#     publish_themes.short_description = "Publish selected themes"


# class ThemeBasePageInline(admin.TabularInline):
#     model = ThemeBasePage
#     extra = 0
#     readonly_fields = ['file_path', 'css_path']


# @admin.register(ThemeBasePage)
# class ThemeBasePageAdmin(admin.ModelAdmin):
#     list_display = ['theme', 'page_name', 'is_required']
#     list_filter = ['is_required', 'theme__status']
#     search_fields = ['theme__name', 'page_name']


# @admin.register(ShopTheme)
# class ShopThemeAdmin(admin.ModelAdmin):
#     list_display = ['shop_id', 'theme', 'is_active', 'is_customized', 'installed_at']
#     list_filter = ['is_active', 'is_customized', 'installed_at']
#     search_fields = ['shop_id', 'theme__name']
#     readonly_fields = ['installed_at', 'activated_at']

#     def get_queryset(self, request):
#         return super().get_queryset(request).select_related('theme')


# class ShopThemePageInline(admin.TabularInline):
#     model = ShopThemePage
#     extra = 0
#     readonly_fields = ['is_customized', 'last_modified']


# @admin.register(ShopThemePage)
# class ShopThemePageAdmin(admin.ModelAdmin):
#     list_display = ['shop_theme', 'page_name', 'is_customized', 'last_modified']
#     list_filter = ['is_customized', 'last_modified']
#     search_fields = ['shop_theme__shop_id', 'page_name']
#     readonly_fields = ['original_content_hash', 'last_modified']


# @admin.register(ThemeReview)
# class ThemeReviewAdmin(admin.ModelAdmin):
#     list_display = ['theme', 'reviewer', 'rating', 'is_approved', 'is_featured', 'created_at']
#     list_filter = ['rating', 'is_approved', 'is_featured', 'created_at']
#     search_fields = ['theme__name', 'reviewer__username', 'title']
#     readonly_fields = ['created_at']

#     actions = ['approve_reviews', 'feature_reviews']

#     def approve_reviews(self, request, queryset):
#         queryset.update(is_approved=True)
#         self.message_user(request, f'{queryset.count()} reviews approved.')
#     approve_reviews.short_description = "Approve selected reviews"

#     def feature_reviews(self, request, queryset):
#         queryset.update(is_featured=True)
#         self.message_user(request, f'{queryset.count()} reviews featured.')
#     feature_reviews.short_description = "Feature selected reviews"


# @admin.register(ThemeCategory)
# class ThemeCategoryAdmin(admin.ModelAdmin):
#     list_display = ['name', 'parent', 'is_active', 'sort_order']
#     list_filter = ['is_active', 'parent']
#     search_fields = ['name', 'description']
#     prepopulated_fields = {'slug': ('name',)}

#     fieldsets = (
#         ('Basic Information', {
#             'fields': ('name', 'slug', 'description', 'icon')
#         }),
#         ('Hierarchy', {
#             'fields': ('parent',)
#         }),
#         ('Display', {
#             'fields': ('is_active', 'sort_order')
#         }),
#     )
