
from django.db import connection
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.urls import reverse
# from .forms import ThemePresetForm, ThemePresetApplyForm
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.http import JsonResponse
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
# from django.contrib.auth.decorators import login_required, staff_member_required
from django.db import transaction
from .models import ThemeSettings, ThemeSettings, StoreSettings, StoreSettingsManager, HeaderSettings, FooterSettings, HomepageLayout, BannerSlide, NavigationMenu, NavigationMenuItem, CustomPage, ProductDisplaySettings, ProductPageSettings, CartSettings, CheckoutSettings, SearchSettings, EmailTemplateSettings, SocialMediaLinks, CustomCSS, ThemePreset, NotificationSettings, MobileAppSettings, BlogSettings, PopupSettings, PerformanceSettings
from .forms import ThemeSettingsForm, ThemePresetForm, BannerSlideForm, BlogSettingsForm, CartSettingsForm, CheckoutSettingsForm, CustomCSSForm, CustomPageForm, EmailTemplateSettingsForm, FooterSettingsForm, HeaderSettingsForm, HomepageLayoutForm, MobileAppSettingsForm, NavigationMenuForm, NavigationMenuItemForm, NotificationSettingsForm, PerformanceSettingsForm, PopupSettingsForm, ProductDisplaySettingsForm, ProductPageSettingsForm, SearchSettingsForm, SocialMediaLinksForm, StoreSettingsForm, ThemePresetApplyForm
from dashboard.decorators import dashboard_prefix_required
from dashboard.sidebar_utiles import main_sidebar

logger = logging.getLogger(__name__)


def _ctx(prefix: str, page_title: str, active_menu: str = "store_theme", **extra):
    context = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix, active_menu),
    }
    context.update(extra)
    return context


@dashboard_prefix_required
def manage_theme_settings(request, prefix):
    """
    Manages the singleton ThemeSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing theme settings for this tenant
    # Since it's a singleton per tenant, we fetch the first available record.
    # If django-tenants is configured correctly, this is scoped to the tenant schema.
    theme_instance = ThemeSettings.objects.first()

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = ThemeSettingsForm(request.POST, instance=theme_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance (creates if new, updates if existing)
                    # Note: If theme_instance was None, form.save() creates a new one.
                    # However, to enforce strict singleton, we might want to ensure
                    # we don't create multiple if logic changes.
                    # For now, ModelForm handles upsert based on instance presence.
                    saved_instance = form.save()

                    messages.success(
                        request, "Theme settings updated successfully.")
                    logger.info(
                        f"Theme settings saved by user {request.user.id}")

                    # Redirect to same page to prevent resubmission
                    return redirect(reverse(f'dashboard:store_settings:manage_theme_settings', kwargs={'prefix': prefix}))
            except Exception as e:
                logger.error(f"Error saving theme settings: {str(e)}")
                messages.error(
                    request, "Failed to save theme settings. Please try again.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # 3. Initial GET Request
        # If no instance exists (new tenant), we initialize the form without an instance
        # allowing the form to create the singleton record upon save.
        form = ThemeSettingsForm(instance=theme_instance)

    # 4. Prepare Context
    # We pass 'object' to align with generic template conventions for Edit/Create
    context = _ctx(
        page_title='Theme Settings',
        active_menu="store_theme",
        form=form,
        object=theme_instance,
        title='Storefront Theme Settings',
        action_url=request.path,  # Current URL for form action
        is_create=theme_instance is None,
        is_edit=theme_instance is not None,
        prefix=prefix,
    )

    # Optional: Generate CSS preview for the admin panel
    if theme_instance:
        context['css_preview'] = theme_instance.generate_css_variables()

    return render(request, 'dashboard/store_settings/manage_theme_settings.html', context)


# # =======================================================================================================================
# # =======================================================================================================================


@dashboard_prefix_required
def theme_preset_list(request, prefix):
    """
    List all available theme presets for the current tenant.
    Allows browsing, filtering, and selecting presets.
    """
    # Get all presets for this tenant (django-tenants handles schema isolation)
    presets = ThemePreset.objects.all()

    # Filtering
    style_filter = request.GET.get('style', '')
    industry_filter = request.GET.get('industry', '')
    featured_only = request.GET.get('featured', '') == 'true'

    if style_filter:
        presets = presets.filter(style=style_filter)
    if industry_filter:
        presets = presets.filter(industry=industry_filter)
    if featured_only:
        presets = presets.filter(is_featured=True)

    # Get counts for filter badges
    style_counts = {
        style[0]: presets.filter(style=style[0]).count()
        for style in ThemePreset.STYLE_CHOICES
    }

    context = {
        'presets': presets,
        'style_counts': style_counts,
        'current_style': style_filter,
        'current_industry': industry_filter,
        'featured_only': featured_only,
        'title': 'Theme Presets Library',
        'ThemePreset': ThemePreset,
    }

    return render(request, 'dashboard/store_settings/theme_preset_list.html', context)


@dashboard_prefix_required
def theme_preset_create(request, prefix):
    """
    Create a new theme preset.
    """
    if request.method == 'POST':
        form = ThemePresetForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                with transaction.atomic():
                    preset = form.save()
                    messages.success(
                        request,
                        f"Theme preset '{preset.name}' created successfully."
                    )
                    logger.info(
                        f"ThemePreset created by user {request.user.id}: {preset.name}"
                    )
                    return redirect(f'dashboard:store_settings:theme_preset_list', prefix=prefix)
            except Exception as e:
                logger.error(f"Error creating theme preset: {str(e)}")
                messages.error(
                    request,
                    "Failed to create theme preset. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ThemePresetForm()

    context = {
        'form': form,
        'title': 'Create Theme Preset',
        'action_url': request.path,
        'is_create': True,
    }

    return render(request, 'dashboard/store_settings/theme_preset_form.html', context)


@dashboard_prefix_required
def theme_preset_edit(request, prefix, pk):
    """
    Edit an existing theme preset.
    """
    preset = get_object_or_404(ThemePreset, pk=pk)

    if request.method == 'POST':
        form = ThemePresetForm(request.POST, request.FILES, instance=preset)

        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    messages.success(
                        request,
                        f"Theme preset '{preset.name}' updated successfully."
                    )
                    logger.info(
                        f"ThemePreset updated by user {request.user.id}: {preset.name}"
                    )
                    return redirect(f'dashboard:store_settings:theme_preset_list', prefix=prefix)
            except Exception as e:
                logger.error(f"Error updating theme preset: {str(e)}")
                messages.error(
                    request,
                    "Failed to update theme preset. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ThemePresetForm(instance=preset)

    context = {
        'form': form,
        'object': preset,
        'title': f'Edit Preset: {preset.name}',
        'action_url': request.path,
        'is_edit': True,
    }

    return render(request, 'dashboard/store_settings/theme_preset_form.html', context)


@dashboard_prefix_required
@require_http_methods(["GET"])
def theme_preset_details(request, prefix, pk):
    """
    Theme preset details endpoint for modal.
    """
    preset = get_object_or_404(ThemePreset, pk=pk)

    context = {"preset": preset}
    return render(request, "dashboard/store_settings/partials/theme_preset_details.html", context)


@dashboard_prefix_required
@require_http_methods(["POST"])
def theme_preset_delete(request, prefix, pk):
    """
    Delete a theme preset.
    """
    preset = get_object_or_404(ThemePreset, pk=pk)
    preset_name = preset.name

    try:
        with transaction.atomic():
            preset.delete()
            messages.success(
                request, f"Theme preset '{preset_name}' deleted successfully.")
            logger.info(
                f"ThemePreset deleted by user {request.user.id}: {preset_name}")
            return JsonResponse({"success": True, "message": "Preset deleted successfully."})
    except Exception as e:
        logger.error(f"Error deleting theme preset: {str(e)}")
        messages.error(
            request, "Failed to delete theme preset. Please try again.")
        return JsonResponse({"success": False, "message": "Failed to delete preset."}, status=400)


# # @dashboard_prefix_required
# @require_POST
# def theme_preset_delete(request, pk):
#     """
#     Delete a theme preset.
#     """
#     preset = get_object_or_404(ThemePreset, pk=pk)
#     preset_name = preset.name
#     try:
#         with transaction.atomic():
#             preset.delete()
#             messages.success(
#                 request,
#                 f"Theme preset '{preset_name}' deleted successfully."
#             )
#             logger.info(
#                 f"ThemePreset deleted by user {request.user.id}: {preset_name}"
#             )
#     except Exception as e:
#         logger.error(f"Error deleting theme preset: {str(e)}")
#         messages.error(request, "Failed to delete theme preset.")
#     return redirect('theme_preset_list')
# # @dashboard_prefix_required
# @require_POST
# def theme_preset_apply(request, pk):
#     """
#     Apply a theme preset to the current tenant's ThemeSettings.
#     This is the key action that copies preset config to active theme.
#     """
#     preset = get_object_or_404(ThemePreset, pk=pk)
#     # Get or create the current theme settings for this tenant
#     theme_settings = ThemeSettings.objects.first()
#     if not theme_settings:
#         theme_settings = ThemeSettings.objects.create()
#     form = ThemePresetApplyForm(request.POST)
#     if form.is_valid():
#         try:
#             with transaction.atomic():
#                 # Apply the preset configuration
#                 preset.apply_to_theme(theme_settings)
#                 messages.success(
#                     request,
#                     f"Theme preset '{preset.name}' applied successfully! "
#                     "Your storefront theme has been updated."
#                 )
#                 logger.info(
#                     f"ThemePreset '{preset.name}' applied to tenant by user {request.user.id}"
#                 )
#                 # Redirect to theme settings to review changes
#                 return redirect('manage_theme_settings')
#         except Exception as e:
#             logger.error(f"Error applying theme preset: {str(e)}")
#             messages.error(
#                 request,
#                 "Failed to apply theme preset. Please try again."
#             )
#     else:
#         messages.error(request, "Confirmation required to apply preset.")
#     return redirect('theme_preset_list')
# # @dashboard_prefix_required
# @require_GET
# def theme_preset_preview(request, pk):
#     """
#     Get preset details as JSON for preview modal.
#     """
#     preset = get_object_or_404(ThemePreset, pk=pk)
#     data = {
#         'id': preset.id,
#         'name': preset.name,
#         'description': preset.description,
#         'style': preset.get_style_display(),
#         'industry': preset.get_industry_display(),
#         'theme_config': preset.theme_config,
#         'is_featured': preset.is_featured,
#         'usage_count': preset.usage_count,
#         'created_at': preset.created_at.isoformat(),
#     }
#     return JsonResponse(data)
# # @dashboard_prefix_required
# def theme_preset_duplicate(request, pk):
#     """
#     Duplicate an existing preset as a starting point for customization.
#     """
#     original = get_object_or_404(ThemePreset, pk=pk)
#     try:
#         with transaction.atomic():
#             # Create a copy
#             duplicate = ThemePreset.objects.create(
#                 name=f"{original.name} (Copy)",
#                 description=f"Copy of {original.description}",
#                 preview_image=original.preview_image,
#                 theme_config=original.theme_config.copy(),
#                 style=original.style,
#                 industry=original.industry,
#                 is_default=False,  # Never duplicate default status
#                 is_featured=False,
#             )
#             messages.success(
#                 request,
#                 f"Preset '{original.name}' duplicated as '{duplicate.name}'."
#             )
#             logger.info(
#                 f"ThemePreset duplicated: {original.name} -> {duplicate.name}"
#             )
#             return redirect('theme_preset_edit', pk=duplicate.pk)
#     except Exception as e:
#         logger.error(f"Error duplicating theme preset: {str(e)}")
#         messages.error(request, "Failed to duplicate preset.")
#         return redirect('theme_preset_list')
# # =========================================================================================================================================================================
# # =========================================================================================================================================================================
# # =========================================================================================================================================================================
# logger = logging.getLogger(__name__)
@dashboard_prefix_required
def manage_store_settings(request, prefix):
    """
    Manages the singleton StoreSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing store settings for this tenant
    # Using the custom manager's get_settings method or fallback to first()
    settings_instance = StoreSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = settings_instance is None
    is_edit = settings_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = StoreSettingsForm(
            request.POST, request.FILES, instance=settings_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    # Invalidate cache
                    cache_key = f'store_settings_{connection.schema_name}'
                    cache.delete(cache_key)

                    messages.success(
                        request, "Store settings updated successfully.")
                    logger.info(
                        f"Store settings saved by user {request.user.id} "
                        f"(tenant: {connection.schema_name})"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_store_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving store settings: {str(e)}")
                messages.error(
                    request, "Failed to save store settings. Please try again.")
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = StoreSettingsForm(instance=settings_instance)

    # 4. Prepare Context
    context = _ctx(
        page_title='Store Settings',
        active_menu="store_settings",
        form=form,
        object=settings_instance,
        title='Store Settings',
        action_url=request.path,
        is_create=is_create,
        is_edit=is_edit,
        schema_name=connection.schema_name,
        prefix=prefix,
        locked_feature_fields=getattr(form, 'locked_feature_fields', []),
    )

    # 5. Add helper data for UI
    if settings_instance:
        context['has_logo'] = bool(settings_instance.logo)
        context['has_logo_dark'] = bool(settings_instance.logo_dark)
        context['has_favicon'] = bool(settings_instance.favicon)
        context['full_address'] = settings_instance.full_address

    return render(request, 'dashboard/store_settings/manage_store_settings.html', context)


# # @dashboard_prefix_required
# def store_settings_section(request, section):
#     """
#     Optional: Render specific sections of store settings via HTMX or AJAX.
#     Useful for large forms with tabbed navigation.
#     """
#     settings_instance = StoreSettings.objects.first()
#     sections = {
#         'general': 'General Settings',
#         'branding': 'Branding & Appearance',
#         'seo': 'SEO & Analytics',
#         'shipping': 'Shipping Settings',
#         'tax': 'Tax Settings',
#         'checkout': 'Checkout Settings',
#         'features': 'Feature Toggles',
#     }
#     if section not in sections:
#         messages.error(request, "Invalid settings section.")
#         return redirect('manage_store_settings')
#     form = StoreSettingsForm(instance=settings_instance)
#     context = {
#         'form': form,
#         'section': section,
#         'section_title': sections[section],
#         'object': settings_instance,
#     }
#     return render(request, 'settings/partials/store_settings_section.html', context)
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# logger = logging.getLogger(__name__)
@dashboard_prefix_required
def manage_social_media_links(request, prefix):
    """
    Manages the singleton SocialMediaLinks for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.
    """
    # 1. Retrieve the existing social media links for this tenant
    social_instance = SocialMediaLinks.objects.first()

    # Determine if this is create or edit mode
    is_create = social_instance is None
    is_edit = social_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = SocialMediaLinksForm(request.POST, instance=social_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    saved_instance = form.save()
                    messages.success(
                        request, "Social media links updated successfully.")
                    logger.info(
                        f"Social media links saved by user {request.user.id}"
                    )
                    return redirect('dashboard:store_settings:manage_social_media_links', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving social media links: {str(e)}")
                messages.error(
                    request,
                    "Failed to save social media links. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = SocialMediaLinksForm(instance=social_instance)

        # Pre-populate sharing_platforms for the form
        if social_instance and social_instance.sharing_platforms:
            form.initial['sharing_platforms'] = social_instance.sharing_platforms

    # 4. Prepare Context - Organize fields by tabs

    context = _ctx(
        form=form,
        page_title='Social Media',
        active_menu="store_social",
        object=social_instance,
        title='Social Media Links',
        action_url=request.path,
        is_create=is_create,
        is_edit=is_edit,
        prefix=prefix,
        # Tab-specific field groups
        social_profiles_fields=[
            form['facebook_url'],
            form['instagram_url'],
            form['twitter_url'],
            form['pinterest_url'],
            form['tiktok_url'],
            form['youtube_url'],
            form['linkedin_url'],
            form['snapchat_url'],
        ],
        whatsapp_field=form['whatsapp_number'],
        sharing_fields={
            'enable_product_sharing': form['enable_product_sharing'],
            'sharing_platforms': form['sharing_platforms'],
            'facebook_app_id': form['facebook_app_id'],
        },
        instagram_fields={
            'show_instagram_feed': form['show_instagram_feed'],
            'instagram_access_token': form['instagram_access_token'],
            'instagram_feed_count': form['instagram_feed_count'],
        },
        visual_fields={
            'icon_style': form['icon_style'],
            'icon_size': form['icon_size'],
        },
    )

    # 5. Add helper data for UI
    if social_instance:
        context['active_platforms'] = social_instance.get_active_platforms()
        context['platform_count'] = len(context['active_platforms'])

    return render(request, 'dashboard/store_settings/manage_social_media.html', context)


# # @dashboard_prefix_required
# def social_media_preview(request,prefix):
#     """
#     Preview how social media links will appear on the storefront.
#     Useful for testing icon styles and sizes.
#     """
#     social_instance = SocialMediaLinks.objects.first()
#     if not social_instance:
#         messages.warning(request, "No social media links configured yet.")
#         return redirect('manage_social_media_links')
#     context = {
#         'object': social_instance,
#         'active_platforms': social_instance.get_active_platforms(),
#         'title': 'Social Media Preview',
#     }
#     return render(request, 'settings/social_media_preview.html', context)
# # @dashboard_prefix_required
# def test_instagram_feed(request,prefix):
#     """
#     Test Instagram feed integration.
#     Validates access token and fetches sample posts.
#     """
#     social_instance = SocialMediaLinks.objects.first()
#     if not social_instance or not social_instance.instagram_access_token:
#         messages.error(request, "Instagram access token not configured.")
#         return redirect('manage_social_media_links')
#     # In production, this would call the Instagram Graph API
#     # For now, we'll just validate the token format
#     token = social_instance.instagram_access_token
#     if len(token) < 50:
#         messages.error(request, "Invalid Instagram access token format.")
#     else:
#         messages.success(
#             request, "Instagram token appears valid. Feed integration ready.")
#     return redirect('manage_social_media_links')
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
@dashboard_prefix_required
def manage_search_settings(request, prefix):
    """
    Manages the singleton SearchSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing search settings for this tenant
    search_instance = SearchSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = search_instance is None
    is_edit = search_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = SearchSettingsForm(request.POST, instance=search_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Search settings updated successfully.")
                    logger.info(
                        f"Search settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_search_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving search settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save search settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = SearchSettingsForm(instance=search_instance)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': search_instance,
        'title': 'Search Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if search_instance:
        # Count enabled search scopes
        scope_count = sum([
            search_instance.search_products,
            search_instance.search_categories,
            search_instance.search_pages,
            search_instance.search_blog_posts,
        ])
        context['enabled_scopes_count'] = scope_count

        # Count enabled autocomplete display options
        display_count = sum([
            search_instance.show_product_images,
            search_instance.show_product_prices,
            search_instance.show_product_ratings,
            search_instance.show_stock_status,
        ])
        context['enabled_display_options'] = display_count

    return render(request, 'dashboard/store_settings/manage_search_settings.html', context)


# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================


# logger = logging.getLogger(__name__)


@dashboard_prefix_required
def manage_product_page_settings(request, prefix):
    """
    Manages the singleton ProductPageSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing product page settings for this tenant
    product_instance = ProductPageSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = product_instance is None
    is_edit = product_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = ProductPageSettingsForm(request.POST, instance=product_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Product page settings updated successfully.")
                    logger.info(
                        f"Product page settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_product_page_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving product page settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save product page settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = ProductPageSettingsForm(instance=product_instance)

    # 4. Prepare Context
    context = _ctx(
        page_title='Product Page Settings',
        active_menu="store_product_page",
        form=form,
        objec=product_instance,
        titl='Product Page Settings',
        action_ur=request.path,
        is_creat=is_create,
        is_edi=is_edit,
        prefix                  =prefix,
    )

    # 5. Add helper data for UI
    if product_instance:
        # Count enabled tabs
        tab_count = sum([
            product_instance.show_description_tab,
            product_instance.show_specifications_tab,
            product_instance.show_shipping_tab,
            product_instance.show_reviews_tab,
            product_instance.show_questions_tab,
        ])
        context['enabled_tabs_count'] = tab_count

        # Count enabled trust badges
        badge_count = sum([
            product_instance.show_secure_checkout_badge,
            product_instance.show_money_back_guarantee,
            product_instance.show_free_shipping_badge,
            product_instance.show_warranty_info,
        ])
        context['enabled_trust_badges'] = badge_count

        # Get layout display name
        context['layout_display'] = product_instance.get_layout_display()

    return render(request, 'dashboard/store_settings/manage_product_page_settings.html', context)


# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================


@dashboard_prefix_required
def manage_product_display_settings(request, prefix):
    """
    Manages the singleton ProductDisplaySettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing product display settings for this tenant
    display_instance = ProductDisplaySettings.objects.first()

    # Determine if this is create or edit mode
    is_create = display_instance is None
    is_edit = display_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = ProductDisplaySettingsForm(
            request.POST, instance=display_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Product display settings updated successfully.")
                    logger.info(
                        f"Product display settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_product_display_settings', prefix=prefix)
            except Exception as e:
                logger.error(
                    f"Error saving product display settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save product display settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = ProductDisplaySettingsForm(instance=display_instance)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': display_instance,
        'title': 'Product Display Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if display_instance:
        # Get display names for choices
        context['card_style_display'] = display_instance.get_card_style_display()
        context['price_display_display'] = display_instance.get_price_display_display()
        context['image_ratio_display'] = display_instance.get_image_ratio_display()
        context['pagination_style_display'] = display_instance.get_pagination_style_display()

        # Count enabled badges
        badge_count = sum([
            display_instance.show_sale_badge,
            display_instance.show_new_badge,
            display_instance.show_stock_status,
            display_instance.show_discount_percentage,
        ])
        context['enabled_badges_count'] = badge_count

        # Count enabled actions
        action_count = sum([
            display_instance.show_add_to_cart_button,
            display_instance.show_quick_view,
            display_instance.show_wishlist_button,
            display_instance.show_compare_button,
        ])
        context['enabled_actions_count'] = action_count

    return render(request, 'dashboard/store_settings/manage_product_display_settings.html', context)


# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================


@dashboard_prefix_required
def manage_popup_settings(request, prefix):
    """
    Manages the singleton PopupSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing popup settings for this tenant
    popup_instance = PopupSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = popup_instance is None
    is_edit = popup_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = PopupSettingsForm(
            request.POST, request.FILES, instance=popup_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Popup settings updated successfully.")
                    logger.info(
                        f"Popup settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_popup_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving popup settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save popup settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = PopupSettingsForm(instance=popup_instance)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': popup_instance,
        'title': 'Popup Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if popup_instance:
        # Get display names for choices
        context['trigger_type_display'] = popup_instance.get_trigger_type_display()
        context['popup_position_display'] = popup_instance.get_popup_position_display()
        context['popup_animation_display'] = popup_instance.get_popup_animation_display()

        # Count enabled features
        feature_count = sum([
            popup_instance.enable_newsletter_popup,
            popup_instance.enable_cookie_consent,
            popup_instance.enable_promo_banner,
            popup_instance.enable_exit_intent,
        ])
        context['enabled_features_count'] = feature_count

        # Check compliance status
        context['gdpr_compliant'] = (
            popup_instance.enable_cookie_consent and
            popup_instance.cookie_policy_url
        )

    return render(request, 'dashboard/store_settings/manage_popup_settings.html', context)


# @dashboard_prefix_required
# def popup_preview(request,prefix):
#     """
#     Preview how popups will appear on the storefront.
#     Useful for testing popup appearance, animations, and triggers.
#     """
#     popup_instance = PopupSettings.objects.first()
#     if not popup_instance:
#         messages.warning(request, "Popup settings not configured yet.")
#         return redirect('manage_popup_settings')
#     context = {
#         'object': popup_instance,
#         'title': 'Popup Preview',
#     }
#     return render(request, 'marketing/popup_preview.html', context)
# @dashboard_prefix_required
# def test_popup_trigger(request,prefix):
#     """
#     Test popup trigger manually.
#     Useful for validating trigger settings without waiting.
#     """
#     popup_instance = PopupSettings.objects.first()
#     if not popup_instance:
#         messages.error(request, "Popup settings not configured.")
#         return redirect('manage_popup_settings')
#     trigger_info = {
#         'type': popup_instance.get_trigger_type_display(),
#         'delay': popup_instance.trigger_delay_seconds,
#         'scroll_percentage': popup_instance.trigger_scroll_percentage,
#         'exit_intent': popup_instance.enable_exit_intent,
#     }
#     messages.success(
#         request,
#         f"Popup trigger configured: {trigger_info['type']} "
#         f"(Delay: {trigger_info['delay']}s, Scroll: {trigger_info['scroll_percentage']}%)"
#     )
#     return redirect('manage_popup_settings')
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# logger = logging.getLogger(__name__)
@dashboard_prefix_required
def manage_performance_settings(request, prefix):
    """
    Manages the singleton PerformanceSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing performance settings for this tenant
    perf_instance = PerformanceSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = perf_instance is None
    is_edit = perf_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = PerformanceSettingsForm(request.POST, instance=perf_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    # Invalidate performance-related cache
                    cache.delete(
                        f'performance_settings_{connection.schema_name}')
                    cache.delete(f'page_cache_{connection.schema_name}')

                    messages.success(
                        request, "Performance settings updated successfully.")
                    logger.info(
                        f"Performance settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_performance_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving performance settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save performance settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = PerformanceSettingsForm(instance=perf_instance)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': perf_instance,
        'title': 'Performance Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if perf_instance:
        # Get display names for choices
        context['cdn_provider_display'] = perf_instance.get_cdn_provider_display()

        # Count enabled optimizations
        optimization_count = sum([
            perf_instance.enable_page_cache,
            perf_instance.enable_browser_cache,
            perf_instance.enable_lazy_loading,
            perf_instance.enable_webp,
            perf_instance.enable_image_compression,
            perf_instance.minify_html,
            perf_instance.minify_css,
            perf_instance.minify_js,
            perf_instance.enable_cdn,
            perf_instance.enable_gzip,
            perf_instance.enable_brotli,
        ])
        context['enabled_optimizations_count'] = optimization_count

        # Calculate performance score (simple heuristic)
        performance_score = 0
        if perf_instance.enable_page_cache:
            performance_score += 15
        if perf_instance.enable_browser_cache:
            performance_score += 10
        if perf_instance.enable_lazy_loading:
            performance_score += 10
        if perf_instance.enable_webp:
            performance_score += 10
        if perf_instance.enable_image_compression:
            performance_score += 10
        if perf_instance.minify_css and perf_instance.minify_js:
            performance_score += 15
        if perf_instance.enable_cdn:
            performance_score += 15
        if perf_instance.enable_brotli or perf_instance.enable_gzip:
            performance_score += 15

        context['performance_score'] = performance_score

        # Performance grade
        if performance_score >= 80:
            context['performance_grade'] = 'A'
            context['performance_grade_color'] = 'emerald'
        elif performance_score >= 60:
            context['performance_grade'] = 'B'
            context['performance_grade_color'] = 'green'
        elif performance_score >= 40:
            context['performance_grade'] = 'C'
            context['performance_grade_color'] = 'yellow'
        elif performance_score >= 20:
            context['performance_grade'] = 'D'
            context['performance_grade_color'] = 'orange'
        else:
            context['performance_grade'] = 'F'
            context['performance_grade_color'] = 'red'

    return render(request, 'dashboard/store_settings/manage_performance_settings.html', context)


# @dashboard_prefix_required
# def performance_test(request,prefix):
#     """
#     Run performance tests and diagnostics.
#     Useful for validating current settings impact.
#     """
#     perf_instance = PerformanceSettings.objects.first()
#     if not perf_instance:
#         messages.warning(request, "Performance settings not configured yet.")
#         return redirect('manage_performance_settings')
#     # Simulate performance diagnostics
#     diagnostics = {
#         'caching_enabled': perf_instance.enable_page_cache,
#         'cdn_enabled': perf_instance.enable_cdn,
#         'compression_enabled': perf_instance.enable_gzip or perf_instance.enable_brotli,
#         'image_optimization': perf_instance.enable_webp and perf_instance.enable_image_compression,
#         'minification': perf_instance.minify_css and perf_instance.minify_js,
#     }
#     enabled_count = sum(diagnostics.values())
#     total_count = len(diagnostics)
#     context = {
#         'object': perf_instance,
#         'diagnostics': diagnostics,
#         'enabled_count': enabled_count,
#         'total_count': total_count,
#         'title': 'Performance Diagnostics',
#     }
#     messages.success(
#         request,
#         f"Performance diagnostics complete: {enabled_count}/{total_count} optimizations active."
#     )
#     return render(request, 'settings/performance_test.html', context)
# @dashboard_prefix_required
# def clear_performance_cache(request,prefix):
#     """
#     Clear all performance-related caches.
#     Useful after making significant changes.
#     """
#     try:
#         # Clear various cache keys
#         cache.delete(f'performance_settings_{connection.schema_name}')
#         cache.delete(f'page_cache_{connection.schema_name}')
#         cache.delete(f'product_cache_{connection.schema_name}')
#         cache.delete(f'category_cache_{connection.schema_name}')
#         messages.success(request, "Performance cache cleared successfully.")
#         logger.info(
#             f"Performance cache cleared by user {request.user.id}"
#         )
#     except Exception as e:
#         logger.error(f"Error clearing cache: {str(e)}")
#         messages.error(request, "Failed to clear cache. Please try again.")
#     return redirect('manage_performance_settings')
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
@dashboard_prefix_required
def manage_notification_settings(request, prefix):
    """
    Manages the singleton NotificationSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing notification settings for this tenant
    notif_instance = NotificationSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = notif_instance is None
    is_edit = notif_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = NotificationSettingsForm(request.POST, instance=notif_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Notification settings updated successfully.")
                    logger.info(
                        f"Notification settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_notification_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving notification settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save notification settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = NotificationSettingsForm(instance=notif_instance)

        # Convert admin emails from list to comma-separated string for display
        if notif_instance and notif_instance.admin_notification_emails:
            form.initial['admin_notification_emails'] = ', '.join(
                notif_instance.admin_notification_emails
            )

    # 4. Prepare Context
    context = {
        'form': form,
        'object': notif_instance,
        'title': 'Notification Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if notif_instance:
        # Count enabled email notifications
        email_count = sum([
            notif_instance.send_order_confirmation,
            notif_instance.send_order_processing,
            notif_instance.send_order_shipped,
            notif_instance.send_order_delivered,
            notif_instance.send_order_cancelled,
            notif_instance.send_order_refunded,
            notif_instance.send_order_on_hold,
            notif_instance.send_welcome_email,
            notif_instance.send_password_reset,
            notif_instance.send_account_verification,
            notif_instance.send_wishlist_reminder,
            notif_instance.send_abandoned_cart,
            notif_instance.send_back_in_stock,
            notif_instance.send_price_drop_alert,
            notif_instance.send_newsletter,
            notif_instance.send_promotional_emails,
        ])
        context['enabled_email_notifications'] = email_count

        # Count enabled SMS notifications
        sms_count = sum([
            notif_instance.sms_order_confirmation,
            notif_instance.sms_order_shipped,
            notif_instance.sms_order_delivered,
            notif_instance.sms_order_cancelled,
            notif_instance.sms_verification_code,
        ])
        context['enabled_sms_notifications'] = sms_count if notif_instance.enable_sms else 0

        # Count enabled admin notifications
        admin_count = sum([
            notif_instance.notify_admin_new_order,
            notif_instance.notify_admin_low_stock,
            notif_instance.notify_admin_out_of_stock,
            notif_instance.notify_admin_new_review,
            notif_instance.notify_admin_new_customer,
            notif_instance.notify_admin_failed_payment,
            notif_instance.notify_admin_refund_request,
        ])
        context['enabled_admin_notifications'] = admin_count

        # Get SMS provider display name
        context['sms_provider_display'] = notif_instance.get_sms_provider_display(
        ) if notif_instance.sms_provider else 'Not Configured'

        # Check SMS configuration status
        context['sms_configured'] = notif_instance.enable_sms and notif_instance.sms_provider

        # Check quiet hours status
        context['quiet_hours_active'] = (
            notif_instance.quiet_hours_enabled and
            notif_instance.quiet_hours_start and
            notif_instance.quiet_hours_end
        )

    return render(request, 'dashboard/store_settings/manage_notification_settings.html', context)

# # @dashboard_prefix_required
# def test_notification(request, notification_type):
#     """
#     Send a test notification to verify configuration.
#     Useful for validating email/SMS settings before going live.
#     """
#     notif_instance = NotificationSettings.objects.first()

#     if not notif_instance:
#         messages.error(request, "Notification settings not configured yet.")
#         return redirect('manage_notification_settings')

#     # Map notification types to settings
#     notification_types = {
#         'order_confirmation': 'send_order_confirmation',
#         'welcome_email': 'send_welcome_email',
#         'abandoned_cart': 'send_abandoned_cart',
#         'admin_new_order': 'notify_admin_new_order',
#         'sms_order_shipped': 'sms_order_shipped',
#     }

#     if notification_type not in notification_types:
#         messages.error(request, "Invalid notification type.")
#         return redirect('manage_notification_settings')

#     # In production, this would actually send a test notification
#     # For now, we'll just validate the setting is enabled
#     setting_attr = notification_types[notification_type]
#     is_enabled = getattr(notif_instance, setting_attr, False)

#     if is_enabled:
#         messages.success(
#             request,
#             f"Test {notification_type.replace('_', ' ')} notification would be sent. "
#             f"(In production, this would send to configured recipients)"
#         )
#     else:
#         messages.warning(
#             request,
#             f"{notification_type.replace('_', ' ').title()} notifications are currently disabled."
#         )

#     return redirect('manage_notification_settings')


# @dashboard_prefix_required
# def notification_logs(request,prefix):
#     """
#     View notification sending logs and history.
#     Useful for debugging and compliance.
#     """
#     # In production, this would query a NotificationLog model
#     # For now, we'll just show a placeholder
#     context = {
#         'title': 'Notification Logs',
#         'logs': [],  # Would be populated from NotificationLog model
#     }
#     return render(request, 'settings/notification_logs.html', context)
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # @dashboard_prefix_required
# def navigation_menu_list(request,prefix):
#     """
#     List all navigation menus for the current tenant.
#     Shows menus grouped by location.
#     """
#     # Get all menus for this tenant (django-tenants handles schema isolation)
#     menus = NavigationMenu.objects.all().select_related().prefetch_related('items')
#     # Group by location
#     menus_by_location = {}
#     for menu in menus:
#         location = menu.get_location_display()
#         if location not in menus_by_location:
#             menus_by_location[location] = []
#         menus_by_location[location].append(menu)
#     context = {
#         'menus': menus,
#         'menus_by_location': menus_by_location,
#         'title': 'Navigation Menus',
#     }
#     return render(request, 'navigation/menu_list.html', context)
# @dashboard_prefix_required
# def navigation_menu_create(request,prefix):
#     """
#     Create a new navigation menu.
#     """
#     if request.method == 'POST':
#         form = NavigationMenuForm(request.POST)
#         if form.is_valid():
#             try:
#                 with transaction.atomic():
#                     menu = form.save()
#                     messages.success(
#                         request,
#                         f"Navigation menu '{menu.name}' created successfully."
#                     )
#                     logger.info(
#                         f"NavigationMenu created by user {request.user.id}: {menu.name}"
#                     )
#                     return redirect('navigation_menu_edit', pk=menu.pk)
#             except Exception as e:
#                 logger.error(f"Error creating navigation menu: {str(e)}")
#                 messages.error(
#                     request,
#                     "Failed to create navigation menu. Please try again."
#                 )
#         else:
#             messages.error(request, "Please correct the errors below.")
#     else:
#         form = NavigationMenuForm()
#     context = {
#         'form': form,
#         'title': 'Create Navigation Menu',
#         'action_url': request.path,
#         'is_create': True,
#     }
#     return render(request, 'navigation/menu_form.html', context)
# @dashboard_prefix_required
# def navigation_menu_edit(request, pk):
#     """
#     Edit an existing navigation menu and its items.
#     """
#     menu = get_object_or_404(NavigationMenu, pk=pk)
#     if request.method == 'POST':
#         form = NavigationMenuForm(request.POST, instance=menu)
#         if form.is_valid():
#             try:
#                 with transaction.atomic():
#                     form.save()
#                     messages.success(
#                         request,
#                         f"Navigation menu '{menu.name}' updated successfully."
#                     )
#                     logger.info(
#                         f"NavigationMenu updated by user {request.user.id}: {menu.name}"
#                     )
#                     return redirect('navigation_menu_list')
#             except Exception as e:
#                 logger.error(f"Error updating navigation menu: {str(e)}")
#                 messages.error(
#                     request,
#                     "Failed to update navigation menu. Please try again."
#                 )
#         else:
#             messages.error(request, "Please correct the errors below.")
#     else:
#         form = NavigationMenuForm(instance=menu)
#     # Get menu items with hierarchy
#     items = menu.items.select_related(
#         'parent').order_by('display_order', 'label')
#     # Build tree structure for display
#     def build_tree(items, parent=None):
#         tree = []
#         for item in items:
#             if item.parent == parent:
#                 children = build_tree(items, parent=item)
#                 tree.append({
#                     'item': item,
#                     'children': children,
#                     'has_children': len(children) > 0,
#                 })
#         return tree
#     item_tree = build_tree(items)
#     context = {
#         'form': form,
#         'object': menu,
#         'items': items,
#         'item_tree': item_tree,
#         'title': f'Edit Menu: {menu.name}',
#         'action_url': request.path,
#         'is_edit': True,
#     }
#     return render(request, 'navigation/menu_edit.html', context)
# @dashboard_prefix_required
# def navigation_menu_delete(request, pk):
#     """
#     Delete a navigation menu and all its items.
#     """
#     menu = get_object_or_404(NavigationMenu, pk=pk)
#     menu_name = menu.name
#     try:
#         with transaction.atomic():
#             # Items will be deleted via CASCADE
#             menu.delete()
#             messages.success(
#                 request,
#                 f"Navigation menu '{menu_name}' deleted successfully."
#             )
#             logger.info(
#                 f"NavigationMenu deleted by user {request.user.id}: {menu_name}"
#             )
#     except Exception as e:
#         logger.error(f"Error deleting navigation menu: {str(e)}")
#         messages.error(request, "Failed to delete navigation menu.")
#     return redirect('navigation_menu_list')
# @dashboard_prefix_required
# def navigation_menu_item_create(request, menu_pk):
#     """
#     Create a new menu item within a specific menu.
#     """
#     menu = get_object_or_404(NavigationMenu, pk=menu_pk)
#     if request.method == 'POST':
#         form = NavigationMenuItemForm(request.POST)
#         if form.is_valid():
#             try:
#                 with transaction.atomic():
#                     item = form.save(commit=False)
#                     item.menu = menu
#                     item.save()
#                     messages.success(
#                         request,
#                         f"Menu item '{item.label}' added successfully."
#                     )
#                     logger.info(
#                         f"NavigationMenuItem created by user {request.user.id}: {item.label}"
#                     )
#                     return redirect('navigation_menu_edit', pk=menu.pk)
#             except Exception as e:
#                 logger.error(f"Error creating menu item: {str(e)}")
#                 messages.error(
#                     request,
#                     "Failed to create menu item. Please try again."
#                 )
#         else:
#             messages.error(request, "Please correct the errors below.")
#     else:
#         form = NavigationMenuItemForm(initial={'menu': menu})
#     context = {
#         'form': form,
#         'menu': menu,
#         'title': 'Add Menu Item',
#         'action_url': request.path,
#         'is_create': True,
#     }
#     return render(request, 'navigation/menu_item_form.html', context)
# @dashboard_prefix_required
# def navigation_menu_item_edit(request, item_pk):
#     """
#     Edit an existing menu item.
#     """
#     item = get_object_or_404(NavigationMenuItem, pk=item_pk)
#     if request.method == 'POST':
#         form = NavigationMenuItemForm(request.POST, instance=item)
#         if form.is_valid():
#             try:
#                 with transaction.atomic():
#                     form.save()
#                     messages.success(
#                         request,
#                         f"Menu item '{item.label}' updated successfully."
#                     )
#                     logger.info(
#                         f"NavigationMenuItem updated by user {request.user.id}: {item.label}"
#                     )
#                     return redirect('navigation_menu_edit', pk=item.menu.pk)
#             except Exception as e:
#                 logger.error(f"Error updating menu item: {str(e)}")
#                 messages.error(
#                     request,
#                     "Failed to update menu item. Please try again."
#                 )
#         else:
#             messages.error(request, "Please correct the errors below.")
#     else:
#         form = NavigationMenuItemForm(instance=item)
#     context = {
#         'form': form,
#         'object': item,
#         'menu': item.menu,
#         'title': f'Edit Item: {item.label}',
#         'action_url': request.path,
#         'is_edit': True,
#     }
#     return render(request, 'navigation/menu_item_form.html', context)
# @dashboard_prefix_required
# def navigation_menu_item_delete(request, item_pk):
#     """
#     Delete a menu item and its children.
#     """
#     item = get_object_or_404(NavigationMenuItem, pk=item_pk)
#     item_label = item.label
#     menu_pk = item.menu.pk
#     try:
#         with transaction.atomic():
#             # Children will be deleted via CASCADE
#             item.delete()
#             messages.success(
#                 request,
#                 f"Menu item '{item_label}' deleted successfully."
#             )
#             logger.info(
#                 f"NavigationMenuItem deleted by user {request.user.id}: {item_label}"
#             )
#     except Exception as e:
#         logger.error(f"Error deleting menu item: {str(e)}")
#         messages.error(request, "Failed to delete menu item.")
#     return redirect('navigation_menu_edit', pk=menu_pk)
# @dashboard_prefix_required
# def navigation_menu_item_reorder(request,prefix):
#     """
#     AJAX endpoint for reordering menu items via drag-and-drop.
#     Expects JSON with item IDs and new order.
#     """
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Method not allowed'}, status=405)
#     try:
#         import json
#         data = json.loads(request.body)
#         items = data.get('items', [])
#         with transaction.atomic():
#             for order, item_data in enumerate(items):
#                 item_id = item_data.get('id')
#                 item = NavigationMenuItem.objects.get(pk=item_id)
#                 item.display_order = order
#                 item.save(update_fields=['display_order'])
#         logger.info(
#             f"Menu items reordered by user {request.user.id}"
#         )
#         return JsonResponse({'success': True, 'message': 'Items reordered successfully.'})
#     except Exception as e:
#         logger.error(f"Error reordering menu items: {str(e)}")
#         return JsonResponse({'error': str(e)}, status=500)
# @dashboard_prefix_required
# def navigation_menu_preview(request, pk):
#     """
#     Preview how a navigation menu will appear on the storefront.
#     """
#     menu = get_object_or_404(NavigationMenu, pk=pk)
#     items = menu.items.filter(is_active=True).select_related(
#         'parent').order_by('display_order')
#     # Build tree structure for preview
#     def build_tree(items, parent=None):
#         tree = []
#         for item in items:
#             if item.parent == parent:
#                 children = build_tree(items, parent=item)
#                 tree.append({
#                     'item': item,
#                     'children': children,
#                     'url': item.get_url(),
#                 })
#         return tree
#     item_tree = build_tree(items)
#     context = {
#         'object': menu,
#         'item_tree': item_tree,
#         'title': 'Menu Preview',
#     }
#     return render(request, 'navigation/menu_preview.html', context)
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# logger = logging.getLogger(__name__)
@dashboard_prefix_required
def manage_mobile_app_settings(request, prefix):
    """
    Manages the singleton MobileAppSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing mobile app settings for this tenant
    app_instance = MobileAppSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = app_instance is None
    is_edit = app_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = MobileAppSettingsForm(
            request.POST, request.FILES, instance=app_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Mobile app settings updated successfully.")
                    logger.info(
                        f"Mobile app settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_mobile_app_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving mobile app settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save mobile app settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = MobileAppSettingsForm(instance=app_instance)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': app_instance,
        'title': 'Mobile App Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if app_instance:
        # Count enabled notification types
        notification_count = sum([
            app_instance.notify_order_updates,
            app_instance.notify_promotions,
            app_instance.notify_new_products,
            app_instance.notify_price_drops,
            app_instance.notify_back_in_stock,
            app_instance.notify_abandoned_cart,
        ])
        context['enabled_notifications_count'] = notification_count

        # Count enabled navigation tabs
        tab_count = sum([
            app_instance.show_home_tab,
            app_instance.show_categories_tab,
            app_instance.show_search_tab,
            app_instance.show_cart_tab,
            app_instance.show_account_tab,
            app_instance.show_wishlist_tab,
        ])
        context['enabled_tabs_count'] = tab_count

        # Count enabled features
        feature_count = sum([
            app_instance.enable_biometric_login,
            app_instance.enable_offline_mode,
            app_instance.enable_barcode_scanner,
            app_instance.enable_ar_preview,
            app_instance.enable_voice_search,
            app_instance.enable_shake_to_refresh,
        ])
        context['enabled_features_count'] = feature_count

        # Push notification status
        context['push_configured'] = (
            app_instance.enable_push_notifications and
            app_instance.firebase_server_key
        )

        # App store links status
        context['app_stores_configured'] = (
            app_instance.app_store_url or app_instance.play_store_url
        )

    return render(request, 'dashboard/store_settings/manage_mobile_app_settings.html', context)


# @dashboard_prefix_required
# def mobile_app_preview(request,prefix):
#     """
#     Preview how the mobile app will appear with current settings.
#     Useful for testing theme, navigation, and features.
#     """
#     app_instance = MobileAppSettings.objects.first()
#     if not app_instance:
#         messages.warning(request, "Mobile app settings not configured yet.")
#         return redirect('manage_mobile_app_settings')
#     context = {
#         'object': app_instance,
#         'title': 'Mobile App Preview',
#     }
#     return render(request, 'mobile/mobile_app_preview.html', context)
# @dashboard_prefix_required
# def test_push_notification(request,prefix):
#     """
#     Send a test push notification to verify configuration.
#     """
#     app_instance = MobileAppSettings.objects.first()
#     if not app_instance:
#         messages.error(request, "Mobile app settings not configured.")
#         return redirect('manage_mobile_app_settings')
#     if not app_instance.enable_push_notifications:
#         messages.warning(request, "Push notifications are currently disabled.")
#         return redirect('manage_mobile_app_settings')
#     if not app_instance.firebase_server_key:
#         messages.error(
#             request,
#             "Firebase server key not configured. Please add it in settings."
#         )
#         return redirect('manage_mobile_app_settings')
#     # In production, this would actually send a test push notification
#     # For now, we'll just validate the configuration
#     messages.success(
#         request,
#         "Test push notification would be sent. (In production, this would send to registered devices)"
#     )
#     return redirect('manage_mobile_app_settings')
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
@dashboard_prefix_required
def manage_homepage_layout(request, prefix):
    """
    Manages the singleton HomepageLayout for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing homepage layout for this tenant
    layout_instance = HomepageLayout.objects.first()

    # Determine if this is create or edit mode
    is_create = layout_instance is None
    is_edit = layout_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = HomepageLayoutForm(request.POST, instance=layout_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Homepage layout updated successfully.")
                    logger.info(
                        f"Homepage layout saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_homepage_layout', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving homepage layout: {str(e)}")
                messages.error(
                    request,
                    "Failed to save homepage layout. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = HomepageLayoutForm(instance=layout_instance)

        # Convert section_order from list to comma-separated string for display
        if layout_instance and layout_instance.section_order:
            form.initial['section_order'] = ', '.join(
                layout_instance.section_order)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': layout_instance,
        'title': 'Homepage Layout',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if layout_instance:
        # Count enabled sections
        enabled_sections = sum([
            layout_instance.show_hero,
            layout_instance.show_featured_categories,
            layout_instance.show_featured_products,
            layout_instance.show_new_arrivals,
            layout_instance.show_best_sellers,
            layout_instance.show_sale_section,
            layout_instance.show_promo_banners,
            layout_instance.show_testimonials,
            layout_instance.show_blog_posts,
            layout_instance.show_instagram_feed,
            layout_instance.show_brands,
        ])
        context['enabled_sections_count'] = enabled_sections

        # Get section order for preview
        context['section_order'] = layout_instance.section_order or layout_instance.get_default_section_order()

        # Hero configuration status
        context['hero_configured'] = (
            layout_instance.show_hero and
            layout_instance.hero_type
        )

    return render(request, 'dashboard/store_settings/manage_homepage_layout.html', context)


# @dashboard_prefix_required
# def homepage_preview(request,prefix):
#     """
#     Preview how the homepage will appear with current layout settings.
#     Useful for testing section order and visibility.
#     """
#     layout_instance = HomepageLayout.objects.first()
#     if not layout_instance:
#         messages.warning(request, "Homepage layout not configured yet.")
#         return redirect('manage_homepage_layout')
#     context = {
#         'object': layout_instance,
#         'section_order': layout_instance.section_order or layout_instance.get_default_section_order(),
#         'title': 'Homepage Preview',
#     }
#     return render(request, 'homepage/homepage_preview.html', context)
# @dashboard_prefix_required
# def reset_homepage_layout(request,prefix):
#     """
#     Reset homepage layout to default configuration.
#     """
#     layout_instance = HomepageLayout.objects.first()
#     try:
#         with transaction.atomic():
#             if layout_instance:
#                 # Reset to defaults
#                 layout_instance.section_order = layout_instance.get_default_section_order()
#                 layout_instance.save()
#                 messages.success(
#                     request, "Homepage layout reset to defaults successfully.")
#                 logger.info(
#                     f"Homepage layout reset by user {request.user.id}"
#                 )
#             else:
#                 messages.warning(request, "No homepage layout to reset.")
#     except Exception as e:
#         logger.error(f"Error resetting homepage layout: {str(e)}")
#         messages.error(request, "Failed to reset homepage layout.")
#     return redirect('manage_homepage_layout')
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# logger = logging.getLogger(__name__)
@dashboard_prefix_required
def manage_header_settings(request, prefix):
    """
    Manages the singleton HeaderSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing header settings for this tenant
    header_instance = HeaderSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = header_instance is None
    is_edit = header_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = HeaderSettingsForm(request.POST, instance=header_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Header settings updated successfully.")
                    logger.info(
                        f"Header settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_header_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving header settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save header settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = HeaderSettingsForm(instance=header_instance)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': header_instance,
        'title': 'Header Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if header_instance:
        # Count enabled header features
        feature_count = sum([
            header_instance.show_announcement_bar,
            header_instance.show_search,
            header_instance.show_cart_icon,
            header_instance.show_account_icon,
            header_instance.show_wishlist_icon,
            header_instance.show_categories_in_nav,
        ])
        context['enabled_features_count'] = feature_count

        # Header configuration status
        context['sticky_enabled'] = header_instance.is_sticky
        context['transparent_enabled'] = header_instance.is_transparent

        # Nav configuration
        context['nav_items_count'] = header_instance.max_nav_items

        # Announcement bar status
        context['announcement_configured'] = (
            header_instance.show_announcement_bar and
            header_instance.announcement_text
        )

    return render(request, 'dashboard/store_settings/manage_header_settings.html', context)


# # @dashboard_prefix_required
# def header_preview(request,prefix):
#     """
#     Preview how the header will appear with current settings.
#     Useful for testing layout, colors, and feature visibility.
#     """
#     header_instance = HeaderSettings.objects.first()

#     if not header_instance:
#         messages.warning(request, "Header settings not configured yet.")
#         return redirect('manage_header_settings')

#     context = {
#         'object': header_instance,
#         'title': 'Header Preview',
#     }

#     return render(request, 'header/header_preview.html', context)


# # @dashboard_prefix_required
# def reset_header_settings(request,prefix):
#     """
#     Reset header settings to default configuration.
#     """
#     header_instance = HeaderSettings.objects.first()

#     try:
#         with transaction.atomic():
#             if header_instance:
#                 # Reset to defaults
#                 header_instance.layout = 'default'
#                 header_instance.is_sticky = True
#                 header_instance.is_transparent = False
#                 header_instance.background_color = '#FFFFFF'
#                 header_instance.text_color = '#000000'
#                 header_instance.height = 80
#                 header_instance.logo_max_width = 180
#                 header_instance.logo_position = 'left'
#                 header_instance.show_announcement_bar = False
#                 header_instance.nav_style = 'horizontal'
#                 header_instance.show_categories_in_nav = True
#                 header_instance.max_nav_items = 7
#                 header_instance.show_search = True
#                 header_instance.search_style = 'icon'
#                 header_instance.show_cart_icon = True
#                 header_instance.cart_icon_style = 'bag'
#                 header_instance.show_cart_count = True
#                 header_instance.cart_preview_on_hover = True
#                 header_instance.show_account_icon = True
#                 header_instance.show_wishlist_icon = True
#                 header_instance.mobile_menu_style = 'slide'
#                 header_instance.save()

#                 messages.success(
#                     request, "Header settings reset to defaults successfully.")
#                 logger.info(
#                     f"Header settings reset by user {request.user.id}"
#                 )
#             else:
#                 messages.warning(request, "No header settings to reset.")
#     except Exception as e:
#         logger.error(f"Error resetting header settings: {str(e)}")
#         messages.error(request, "Failed to reset header settings.")

#     return redirect('manage_header_settings')

# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================


# logger = logging.getLogger(__name__)


@dashboard_prefix_required
def manage_footer_settings(request, prefix):
    """
    Manages the singleton FooterSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing footer settings for this tenant
    footer_instance = FooterSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = footer_instance is None
    is_edit = footer_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = FooterSettingsForm(
            request.POST, request.FILES, instance=footer_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Footer settings updated successfully.")
                    logger.info(
                        f"Footer settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_footer_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving footer settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save footer settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = FooterSettingsForm(instance=footer_instance)

        # Convert accepted_payments from list to comma-separated string for display
        if footer_instance and footer_instance.accepted_payments:
            form.initial['accepted_payments'] = ', '.join(
                footer_instance.accepted_payments)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': footer_instance,
        'title': 'Footer Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if footer_instance:
        # Count enabled footer features
        feature_count = sum([
            footer_instance.show_logo,
            footer_instance.show_newsletter,
            footer_instance.show_payment_icons,
            footer_instance.show_social_links,
            footer_instance.show_trust_badges,
            footer_instance.show_legal_links,
        ])
        context['enabled_features_count'] = feature_count

        # Count trust badges
        badge_count = sum([
            bool(footer_instance.trust_badge_1),
            bool(footer_instance.trust_badge_2),
            bool(footer_instance.trust_badge_3),
        ])
        context['trust_badges_count'] = badge_count

        # Footer configuration status
        context['newsletter_configured'] = (
            footer_instance.show_newsletter and
            footer_instance.newsletter_title
        )

        # Payment methods count
        context['payment_methods_count'] = len(
            footer_instance.accepted_payments) if footer_instance.accepted_payments else 0

    return render(request, 'dashboard/store_settings/manage_footer_settings.html', context)


# # @dashboard_prefix_required
# def footer_preview(request,prefix):
#     """
#     Preview how the footer will appear with current settings.
#     Useful for testing layout, colors, and feature visibility.
#     """
#     footer_instance = FooterSettings.objects.first()

#     if not footer_instance:
#         messages.warning(request, "Footer settings not configured yet.")
#         return redirect('manage_footer_settings')

#     context = {
#         'object': footer_instance,
#         'title': 'Footer Preview',
#     }

#     return render(request, 'footer/footer_preview.html', context)


# # @dashboard_prefix_required
# def reset_footer_settings(request,prefix):
#     """
#     Reset footer settings to default configuration.
#     """
#     footer_instance = FooterSettings.objects.first()

#     try:
#         with transaction.atomic():
#             if footer_instance:
#                 # Reset to defaults
#                 footer_instance.layout = '4_columns'
#                 footer_instance.background_color = '#1F2937'
#                 footer_instance.text_color = '#FFFFFF'
#                 footer_instance.show_logo = True
#                 footer_instance.about_text = ''
#                 footer_instance.copyright_text = ''
#                 footer_instance.show_newsletter = True
#                 footer_instance.newsletter_title = 'Subscribe to our newsletter'
#                 footer_instance.newsletter_description = 'Get the latest updates on new products and upcoming sales'
#                 footer_instance.show_payment_icons = True
#                 footer_instance.accepted_payments = [
#                     'visa', 'mastercard', 'paypal', 'apple_pay', 'google_pay']
#                 footer_instance.show_social_links = True
#                 footer_instance.social_links_style = 'icons'
#                 footer_instance.show_trust_badges = False
#                 footer_instance.show_legal_links = True
#                 footer_instance.save()

#                 messages.success(
#                     request, "Footer settings reset to defaults successfully.")
#                 logger.info(
#                     f"Footer settings reset by user {request.user.id}"
#                 )
#             else:
#                 messages.warning(request, "No footer settings to reset.")
#     except Exception as e:
#         logger.error(f"Error resetting footer settings: {str(e)}")
#         messages.error(request, "Failed to reset footer settings.")

#     return redirect('manage_footer_settings')

# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================


# logger = logging.getLogger(__name__)


@dashboard_prefix_required
def manage_email_template_settings(request, prefix):
    """
    Manages the singleton EmailTemplateSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.

    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing email template settings for this tenant
    email_instance = EmailTemplateSettings.objects.first()

    # Determine if this is create or edit mode
    is_create = email_instance is None
    is_edit = email_instance is not None

    # 2. Handle Form Submission
    if request.method == 'POST':
        form = EmailTemplateSettingsForm(
            request.POST, request.FILES, instance=email_instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()

                    messages.success(
                        request, "Email template settings updated successfully.")
                    logger.info(
                        f"Email template settings saved by user {request.user.id}"
                    )

                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_email_template_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving email template settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save email template settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = EmailTemplateSettingsForm(instance=email_instance)

    # 4. Prepare Context
    context = {
        'form': form,
        'object': email_instance,
        'title': 'Email Template Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }

    # 5. Add helper data for UI
    if email_instance:
        # Count enabled email features
        feature_count = sum([
            email_instance.show_social_links_in_header,
            email_instance.show_social_links_in_footer,
            email_instance.show_contact_info,
            email_instance.show_unsubscribe_link,
            bool(email_instance.header_text),
            bool(email_instance.footer_text),
        ])
        context['enabled_features_count'] = feature_count

        # Email configuration status
        context['logo_configured'] = bool(email_instance.logo)
        context['custom_messages_count'] = sum([
            bool(email_instance.order_confirmation_custom_message),
            bool(email_instance.shipping_notification_custom_message),
        ])

        # Compliance status
        context['gdpr_compliant'] = email_instance.show_unsubscribe_link

    return render(request, 'dashboard/store_settings/manage_email_template_settings.html', context)


# # @dashboard_prefix_required
# def email_template_preview(request, email_type=None):
#     """
#     Preview how email templates will appear with current settings.
#     Supports different email types (order, shipping, welcome, etc.).
#     """
#     email_instance = EmailTemplateSettings.objects.first()

#     if not email_instance:
#         messages.warning(
#             request, "Email template settings not configured yet.")
#         return redirect('manage_email_template_settings')

#     # Default to order confirmation if no type specified
#     if not email_type or email_type not in ['order_confirmation', 'shipping_notification', 'password_reset', 'welcome', 'abandoned_cart']:
#         email_type = 'order_confirmation'

#     context = {
#         'object': email_instance,
#         'email_type': email_type,
#         'title': 'Email Template Preview',
#     }

#     return render(request, 'emails/email_template_preview.html', context)


# # @dashboard_prefix_required
# def send_test_email(request, email_type=None):
#     """
#     Send a test email to verify template configuration.
#     """
#     email_instance = EmailTemplateSettings.objects.first()

#     if not email_instance:
#         messages.error(request, "Email template settings not configured.")
#         return redirect('manage_email_template_settings')

#     if not email_type or email_type not in ['order_confirmation', 'shipping_notification', 'password_reset', 'welcome', 'abandoned_cart']:
#         email_type = 'order_confirmation'

#     # In production, this would actually send a test email
#     # For now, we'll just validate the configuration
#     if not email_instance.logo:
#         messages.warning(
#             request, "No logo configured - email will use default branding.")

#     messages.success(
#         request,
#         f"Test {email_type.replace('_', ' ')} email would be sent. (In production, this would send to configured test address)"
#     )

#     return redirect('manage_email_template_settings')


# # @dashboard_prefix_required
# def reset_email_template_settings(request,prefix):
#     """
#     Reset email template settings to default configuration.
#     """
#     email_instance = EmailTemplateSettings.objects.first()

#     try:
#         with transaction.atomic():
#             if email_instance:
#                 # Reset to defaults
#                 email_instance.accent_color = '#2563EB'
#                 email_instance.background_color = '#F3F4F6'
#                 email_instance.content_background_color = '#FFFFFF'
#                 email_instance.text_color = '#1F2937'
#                 email_instance.header_text = ''
#                 email_instance.show_social_links_in_header = False
#                 email_instance.footer_text = ''
#                 email_instance.show_contact_info = True
#                 email_instance.show_social_links_in_footer = True
#                 email_instance.show_unsubscribe_link = True
#                 email_instance.button_style = 'solid'
#                 email_instance.button_border_radius = 6
#                 email_instance.font_family = 'system'
#                 email_instance.order_confirmation_custom_message = ''
#                 email_instance.shipping_notification_custom_message = ''
#                 email_instance.save()

#                 messages.success(
#                     request, "Email template settings reset to defaults successfully.")
#                 logger.info(
#                     f"Email template settings reset by user {request.user.id}"
#                 )
#             else:
#                 messages.warning(
#                     request, "No email template settings to reset.")
#     except Exception as e:
#         logger.error(f"Error resetting email template settings: {str(e)}")
#         messages.error(request, "Failed to reset email template settings.")

#     return redirect('manage_email_template_settings')

# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================


# logger = logging.getLogger(__name__)


# # @dashboard_prefix_required
# def custom_page_list(request,prefix):
#     """
#     List all custom pages with filtering and search.
#     Shows page status, template, and last updated date.
#     """
#     # Get all pages for this tenant (django-tenants handles schema isolation)
#     pages = CustomPage.objects.all()

#     # Filtering
#     status_filter = request.GET.get('status', '')
#     template_filter = request.GET.get('template', '')
#     search_query = request.GET.get('search', '')

#     if status_filter:
#         pages = pages.filter(status=status_filter)
#     if template_filter:
#         pages = pages.filter(template=template_filter)
#     if search_query:
#         pages = pages.filter(
#             Q(title__icontains=search_query) |
#             Q(slug__icontains=search_query) |
#             Q(content__icontains=search_query)
#         )

#     # Get counts for filter badges
#     status_counts = {
#         'published': pages.filter(status='published').count(),
#         'draft': pages.filter(status='draft').count(),
#         'hidden': pages.filter(status='hidden').count(),
#     }

#     # Get counts for bulk action form
#     total_count = pages.count()

#     context = {
#         'pages': pages,
#         'status_counts': status_counts,
#         'total_count': total_count,
#         'current_status': status_filter,
#         'current_template': template_filter,
#         'search_query': search_query,
#         'title': 'Custom Pages',
#         'bulk_form': CustomPageBulkActionForm(),
#     }

#     return render(request, 'pages/custom_page_list.html', context)


@dashboard_prefix_required
def custom_page_create(request, prefix):
    """
    Create a new custom page.
    """
    if request.method == 'POST':
        form = CustomPageForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                with transaction.atomic():
                    page = form.save()
                    messages.success(
                        request,
                        f"Page '{page.title}' created successfully."
                    )
                    logger.info(
                        f"CustomPage created by user {request.user.id}: {page.title} (slug: {page.slug})"
                    )
                    return redirect('dashboard:store_settings:custom_page_edit', prefix=prefix, pk=page.pk)
            except Exception as e:
                logger.error(f"Error creating custom page: {str(e)}")
                messages.error(
                    request,
                    "Failed to create page. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        form = CustomPageForm()

    context = {
        'form': form,
        'title': 'Create Page',
        'action_url': request.path,
        'is_create': True,
    }

    return render(request, 'dashboard/store_settings/custom_page_form.html', context)


@dashboard_prefix_required
def custom_page_edit(request, prefix, pk):
    """
    Edit an existing custom page.
    """
    page = get_object_or_404(CustomPage, pk=pk)

    if request.method == 'POST':
        form = CustomPageForm(request.POST, request.FILES, instance=page)

        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    messages.success(
                        request,
                        f"Page '{page.title}' updated successfully."
                    )
                    logger.info(
                        f"CustomPage updated by user {request.user.id}: {page.title}"
                    )
                    return redirect('dashboard:store_settings:custom_page_list', prefix=prefix)
            except Exception as e:
                logger.error(f"Error updating custom page: {str(e)}")
                messages.error(
                    request,
                    "Failed to update page. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        form = CustomPageForm(instance=page)

    context = {
        'form': form,
        'object': page,
        'title': f'Edit Page: {page.title}',
        'action_url': request.path,
        'is_edit': True,
    }

    return render(request, 'dashboard/store_settings/custom_page_form.html', context)


# # @dashboard_prefix_required
# def custom_page_delete(request, pk):
#     """
#     Delete a custom page.
#     """
#     page = get_object_or_404(CustomPage, pk=pk)
#     page_title = page.title

#     try:
#         with transaction.atomic():
#             page.delete()
#             messages.success(
#                 request,
#                 f"Page '{page_title}' deleted successfully."
#             )
#             logger.info(
#                 f"CustomPage deleted by user {request.user.id}: {page_title}"
#             )
#     except Exception as e:
#         logger.error(f"Error deleting custom page: {str(e)}")
#         messages.error(request, "Failed to delete page.")

#     return redirect('custom_page_list')


# # @dashboard_prefix_required
# def custom_page_duplicate(request, pk):
#     """
#     Duplicate an existing custom page as a starting point for new content.
#     """
#     original = get_object_or_404(CustomPage, pk=pk)

#     try:
#         with transaction.atomic():
#             # Create a copy with modified title and slug
#             page = CustomPage.objects.create(
#                 title=f"{original.title} (Copy)",
#                 slug=f"{original.slug}-copy",
#                 content=original.content,
#                 excerpt=original.excerpt,
#                 template=original.template,
#                 show_title=original.show_title,
#                 show_breadcrumbs=original.show_breadcrumbs,
#                 featured_image=original.featured_image,
#                 meta_title=original.meta_title,
#                 meta_description=original.meta_description,
#                 status='draft',  # Always start as draft
#             )

#             messages.success(
#                 request,
#                 f"Page '{original.title}' duplicated as '{page.title}'."
#             )
#             logger.info(
#                 f"CustomPage duplicated: {original.title} -> {page.title}"
#             )

#             return redirect('custom_page_edit', pk=page.pk)
#     except Exception as e:
#         logger.error(f"Error duplicating custom page: {str(e)}")
#         messages.error(request, "Failed to duplicate page.")
#         return redirect('custom_page_list')


# # @dashboard_prefix_required
# def custom_page_preview(request, pk):
#     """
#     Preview how a custom page will appear on the storefront.
#     """
#     page = get_object_or_404(CustomPage, pk=pk)

#     context = {
#         'object': page,
#         'title': f'Preview: {page.title}',
#         'is_preview': True,
#     }

#     return render(request, 'pages/custom_page_preview.html', context)


# # @dashboard_prefix_required
# def custom_page_bulk_action(request,prefix):
#     """
#     Perform bulk actions on multiple pages.
#     Expects POST with action and page_ids.
#     """
#     if request.method != 'POST':
#         return redirect('custom_page_list')

#     form = CustomPageBulkActionForm(request.POST)

#     if form.is_valid():
#         action = form.cleaned_data.get('action')
#         page_ids = request.POST.getlist('page_ids')

#         if not page_ids:
#             messages.warning(request, "No pages selected.")
#             return redirect('custom_page_list')

#         try:
#             with transaction.atomic():
#                 pages = CustomPage.objects.filter(pk__in=page_ids)
#                 count = pages.count()

#                 if action == 'publish':
#                     pages.update(
#                         status='published',
#                         published_at=timezone.now()
#                     )
#                     messages.success(request, f"{count} page(s) published.")

#                 elif action == 'draft':
#                     pages.update(status='draft')
#                     messages.success(
#                         request, f"{count} page(s) moved to draft.")

#                 elif action == 'hide':
#                     pages.update(status='hidden')
#                     messages.success(request, f"{count} page(s) hidden.")

#                 elif action == 'delete':
#                     pages.delete()
#                     messages.success(request, f"{count} page(s) deleted.")

#                 logger.info(
#                     f"Bulk action '{action}' performed on {count} pages by user {request.user.id}"
#                 )

#         except Exception as e:
#             logger.error(f"Error performing bulk action: {str(e)}")
#             messages.error(request, "Failed to perform bulk action.")

#     else:
#         messages.error(request, "Invalid action.")

#     return redirect('custom_page_list')


# # @dashboard_prefix_required
# def custom_page_stats(request,prefix):
#     """
#     Get page statistics for dashboard widgets.
#     Returns JSON data.
#     """
#     stats = {
#         'total': CustomPage.objects.count(),
#         'published': CustomPage.objects.filter(status='published').count(),
#         'draft': CustomPage.objects.filter(status='draft').count(),
#         'hidden': CustomPage.objects.filter(status='hidden').count(),
#         'recently_updated': CustomPage.objects.filter(
#             updated_at__gte=timezone.now().timezone.timedelta(days=7)
#         ).count(),
#     }

#     # Most common templates
#     template_counts = CustomPage.objects.values('template').annotate(
#         count=Count('template')
#     ).order_by('-count')[:5]

#     stats['templates'] = list(template_counts)

#     return JsonResponse(stats)

# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================


# logger = logging.getLogger(__name__)


# # @dashboard_prefix_required
# def custom_css_list(request,prefix):
#     """
#     List all custom CSS snippets with filtering and search.
#     Shows snippet status, target pages, and load order.
#     """
#     # Get all CSS snippets for this tenant (django-tenants handles schema isolation)
#     css_snippets = CustomCSS.objects.all()

#     # Filtering
#     status_filter = request.GET.get('status', '')
#     target_filter = request.GET.get('target', '')
#     search_query = request.GET.get('search', '')

#     if status_filter:
#         css_snippets = css_snippets.filter(
#             is_active=(status_filter == 'active'))
#     if target_filter:
#         css_snippets = css_snippets.filter(apply_to=target_filter)
#     if search_query:
#         css_snippets = css_snippets.filter(
#             Q(name__icontains=search_query) |
#             Q(description__icontains=search_query) |
#             Q(css_code__icontains=search_query)
#         )

#     # Get counts for filter badges
#     status_counts = {
#         'active': css_snippets.filter(is_active=True).count(),
#         'inactive': css_snippets.filter(is_active=False).count(),
#     }

#     # Get counts for bulk action form
#     total_count = css_snippets.count()

#     context = {
#         'css_snippets': css_snippets,
#         'status_counts': status_counts,
#         'total_count': total_count,
#         'current_status': status_filter,
#         'current_target': target_filter,
#         'search_query': search_query,
#         'title': 'Custom CSS',
#         'bulk_form': CustomCSSBulkActionForm(),
#     }

#     return render(request, 'css/custom_css_list.html', context)


@dashboard_prefix_required
def custom_css_create(request, prefix):
    """
    Create a new custom CSS snippet.
    """
    if request.method == 'POST':
        form = CustomCSSForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    css = form.save(commit=False)
                    css.created_by = request.user.username
                    css.save()
                    messages.success(
                        request,
                        f"CSS snippet '{css.name}' created successfully."
                    )
                    logger.info(
                        f"CustomCSS created by user {request.user.id}: {css.name}"
                    )
                    return redirect('dashboard:store_settings:custom_css_edit', prefix=prefix, pk=css.pk)
            except Exception as e:
                logger.error(f"Error creating custom CSS: {str(e)}")
                messages.error(
                    request,
                    "Failed to create CSS snippet. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        form = CustomCSSForm()
    context = {
        'form': form,
        'title': 'Create CSS Snippet',
        'action_url': request.path,
        'is_create': True,
    }
    return render(request, 'dashboard/store_settings/custom_css_form.html', context)


@dashboard_prefix_required
def custom_css_edit(request, pk):
    """
    Edit an existing custom CSS snippet.
    """
    css = get_object_or_404(CustomCSS, pk=pk)
    if request.method == 'POST':
        form = CustomCSSForm(request.POST, instance=css)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    messages.success(
                        request,
                        f"CSS snippet '{css.name}' updated successfully."
                    )
                    logger.info(
                        f"CustomCSS updated by user {request.user.id}: {css.name}"
                    )
                    return redirect('dashboard:store_settings:custom_css_list', prefix=prefix)
            except Exception as e:
                logger.error(f"Error updating custom CSS: {str(e)}")
                messages.error(
                    request,
                    "Failed to update CSS snippet. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        form = CustomCSSForm(instance=css)
        # Convert custom_pages from list to comma-separated string for display
        if css.custom_pages:
            form.initial['custom_pages'] = ', '.join(
                str(p) for p in css.custom_pages)
    context = {
        'form': form,
        'object': css,
        'title': f'Edit CSS: {css.name}',
        'action_url': request.path,
        'is_edit': True,
    }
    return render(request, 'dashboard/store_settings/custom_css_form.html', context)

# # @dashboard_prefix_required
# def custom_css_delete(request, pk):
#     """
#     Delete a custom CSS snippet.
#     """
#     css = get_object_or_404(CustomCSS, pk=pk)
#     css_name = css.name
#     try:
#         with transaction.atomic():
#             css.delete()
#             messages.success(
#                 request,
#                 f"CSS snippet '{css_name}' deleted successfully."
#             )
#             logger.info(
#                 f"CustomCSS deleted by user {request.user.id}: {css_name}"
#             )
#     except Exception as e:
#         logger.error(f"Error deleting custom CSS: {str(e)}")
#         messages.error(request, "Failed to delete CSS snippet.")
#     return redirect('custom_css_list')
# # @dashboard_prefix_required
# def custom_css_duplicate(request, pk):
#     """
#     Duplicate an existing CSS snippet as a starting point for new styles.
#     """
#     original = get_object_or_404(CustomCSS, pk=pk)
#     try:
#         with transaction.atomic():
#             # Create a copy with modified name
#             css = CustomCSS.objects.create(
#                 name=f"{original.name} (Copy)",
#                 css_code=original.css_code,
#                 description=original.description,
#                 apply_to=original.apply_to,
#                 custom_pages=original.custom_pages,
#                 apply_to_mobile=original.apply_to_mobile,
#                 apply_to_tablet=original.apply_to_tablet,
#                 apply_to_desktop=original.apply_to_desktop,
#                 is_active=False,  # Always start as inactive
#                 load_order=original.load_order,
#                 created_by=request.user.username,
#             )
#             messages.success(
#                 request,
#                 f"CSS snippet '{original.name}' duplicated as '{css.name}'."
#             )
#             logger.info(
#                 f"CustomCSS duplicated: {original.name} -> {css.name}"
#             )
#             return redirect('custom_css_edit', pk=css.pk)
#     except Exception as e:
#         logger.error(f"Error duplicating custom CSS: {str(e)}")
#         messages.error(request, "Failed to duplicate CSS snippet.")
#         return redirect('custom_css_list')
# # @dashboard_prefix_required
# def custom_css_preview(request, pk):
#     """
#     Preview how CSS will be rendered with media queries.
#     """
#     css = get_object_or_404(CustomCSS, pk=pk)
#     context = {
#         'object': css,
#         'rendered_css': css.render_css(),
#         'title': f'Preview CSS: {css.name}',
#     }
#     return render(request, 'css/custom_css_preview.html', context)
# # @dashboard_prefix_required
# def custom_css_bulk_action(request,prefix):
#     """
#     Perform bulk actions on multiple CSS snippets.
#     Expects POST with action and css_ids.
#     """
#     if request.method != 'POST':
#         return redirect('custom_css_list')
#     form = CustomCSSBulkActionForm(request.POST)
#     if form.is_valid():
#         action = form.cleaned_data.get('action')
#         css_ids = request.POST.getlist('css_ids')
#         if not css_ids:
#             messages.warning(request, "No CSS snippets selected.")
#             return redirect('custom_css_list')
#         try:
#             with transaction.atomic():
#                 snippets = CustomCSS.objects.filter(pk__in=css_ids)
#                 count = snippets.count()
#                 if action == 'activate':
#                     snippets.update(is_active=True)
#                     messages.success(request, f"{count} snippet(s) activated.")
#                 elif action == 'deactivate':
#                     snippets.update(is_active=False)
#                     messages.success(
#                         request, f"{count} snippet(s) deactivated.")
#                 elif action == 'delete':
#                     snippets.delete()
#                     messages.success(request, f"{count} snippet(s) deleted.")
#                 logger.info(
#                     f"Bulk action '{action}' performed on {count} CSS snippets by user {request.user.id}"
#                 )
#         except Exception as e:
#             logger.error(f"Error performing bulk action: {str(e)}")
#             messages.error(request, "Failed to perform bulk action.")
#     else:
#         messages.error(request, "Invalid action.")
#     return redirect('custom_css_list')
# # @dashboard_prefix_required
# def custom_css_stats(request,prefix):
#     """
#     Get CSS statistics for dashboard widgets.
#     Returns JSON data.
#     """
#     stats = {
#         'total': CustomCSS.objects.count(),
#         'active': CustomCSS.objects.filter(is_active=True).count(),
#         'inactive': CustomCSS.objects.filter(is_active=False).count(),
#     }
#     # Most common targets
#     target_counts = CustomCSS.objects.values('apply_to').annotate(
#         count=Count('apply_to')
#     ).order_by('-count')[:5]
#     stats['targets'] = list(target_counts)
#     return JsonResponse(stats)
# # @dashboard_prefix_required
# def validate_css_syntax(request,prefix):
#     """
#     AJAX endpoint to validate CSS syntax before saving.
#     Returns JSON with validation results.
#     """
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Method not allowed'}, status=405)
#     import json
#     try:
#         data = json.loads(request.body)
#         css_code = data.get('css_code', '')
#         # Basic validation
#         errors = []
#         warnings = []
#         # Check for balanced braces
#         open_braces = css_code.count('{')
#         close_braces = css_code.count('}')
#         if open_braces != close_braces:
#             errors.append(
#                 f"Unbalanced braces: {open_braces} open, {close_braces} close")
#         # Security checks
#         dangerous_patterns = [
#             (r'<script', 'Script tags detected'),
#             (r'javascript:', 'JavaScript URLs detected'),
#             (r'expression\s*\(', 'CSS expressions detected'),
#             (r'@import', '@import rules detected'),
#         ]
#         for pattern, message in dangerous_patterns:
#             if re.search(pattern, css_code, re.IGNORECASE):
#                 errors.append(f"Security violation: {message}")
#         # Size warning
#         if len(css_code) > 50000:
#             warnings.append(
#                 f"Large CSS ({len(css_code)} chars) - may impact performance")
#         return JsonResponse({
#             'valid': len(errors) == 0,
#             'errors': errors,
#             'warnings': warnings,
#         })
#     except Exception as e:
#         logger.error(f"Error validating CSS: {str(e)}")
#         return JsonResponse({'error': str(e)}, status=500)
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# logger = logging.getLogger(__name__)


@dashboard_prefix_required
def manage_checkout_settings(request, prefix):
    """
    Manages the singleton CheckoutSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.
    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing checkout settings for this tenant
    checkout_instance = CheckoutSettings.objects.first()
    # Determine if this is create or edit mode
    is_create = checkout_instance is None
    is_edit = checkout_instance is not None
    # 2. Handle Form Submission
    if request.method == 'POST':
        form = CheckoutSettingsForm(request.POST, instance=checkout_instance)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()
                    messages.success(
                        request, "Checkout settings updated successfully.")
                    logger.info(
                        f"Checkout settings saved by user {request.user.id}"
                    )
                    # Redirect to same page to prevent resubmission
                    return redirect('dashboard:store_settings:manage_checkout_settings', prefix=prefix)
            except Exception as e:
                logger.error(f"Error saving checkout settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save checkout settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = CheckoutSettingsForm(instance=checkout_instance)
    # 4. Prepare Context
    context = {
        'form': form,
        'object': checkout_instance,
        'title': 'Checkout Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }
    # 5. Add helper data for UI
    if checkout_instance:
        # Count enabled checkout features
        feature_count = sum([
            checkout_instance.show_breadcrumbs,
            checkout_instance.show_order_summary,
            checkout_instance.allow_guest_checkout,
            checkout_instance.show_newsletter_signup,
            checkout_instance.show_shipping_calculator,
            checkout_instance.show_payment_icons,
            checkout_instance.show_trust_badges,
            checkout_instance.enable_coupon_codes,
            checkout_instance.show_related_products,
            checkout_instance.show_terms_checkbox,
        ])
        context['enabled_features_count'] = feature_count
        # Checkout flow status
        context['checkout_flow'] = checkout_instance.get_checkout_style_display()
        # Account requirement status
        context['account_required'] = checkout_instance.require_account_creation
        context['guest_allowed'] = checkout_instance.allow_guest_checkout
        # Conversion optimization score (simple heuristic)
        conversion_score = 0
        if checkout_instance.allow_guest_checkout:
            conversion_score += 20
        if checkout_instance.show_trust_badges:
            conversion_score += 15
        if checkout_instance.enable_coupon_codes:
            conversion_score += 10
        if checkout_instance.show_order_summary:
            conversion_score += 15
        if checkout_instance.show_breadcrumbs:
            conversion_score += 10
        if checkout_instance.show_shipping_calculator:
            conversion_score += 15
        if checkout_instance.show_estimated_total:
            conversion_score += 15
        context['conversion_score'] = conversion_score
    return render(request, 'dashboard/store_settings/manage_checkout_settings.html', context)


# # @dashboard_prefix_required
# def checkout_preview(request,prefix):
#     """
#     Preview how the checkout will appear with current settings.
#     Useful for testing checkout flow and feature visibility.
#     """
#     checkout_instance = CheckoutSettings.objects.first()
#     if not checkout_instance:
#         messages.warning(request, "Checkout settings not configured yet.")
#         return redirect('manage_checkout_settings')
#     context = {
#         'object': checkout_instance,
#         'title': 'Checkout Preview',
#     }
#     return render(request, 'checkout/checkout_preview.html', context)
# # @dashboard_prefix_required
# def reset_checkout_settings(request,prefix):
#     """
#     Reset checkout settings to default configuration.
#     """
#     checkout_instance = CheckoutSettings.objects.first()
#     try:
#         with transaction.atomic():
#             if checkout_instance:
#                 # Reset to defaults
#                 checkout_instance.checkout_style = 'multi_step'
#                 checkout_instance.show_breadcrumbs = True
#                 checkout_instance.show_order_summary = True
#                 checkout_instance.order_summary_collapsible = True
#                 checkout_instance.require_account_creation = False
#                 checkout_instance.allow_guest_checkout = True
#                 checkout_instance.show_newsletter_signup = True
#                 checkout_instance.newsletter_opt_in_default = False
#                 checkout_instance.require_phone_number = True
#                 checkout_instance.require_company_name = False
#                 checkout_instance.require_address_line2 = False
#                 checkout_instance.show_delivery_instructions = True
#                 checkout_instance.show_shipping_calculator = True
#                 checkout_instance.group_shipping_methods = True
#                 checkout_instance.show_payment_icons = True
#                 checkout_instance.show_trust_badges = True
#                 checkout_instance.enable_cart_notes = True
#                 checkout_instance.enable_coupon_codes = True
#                 checkout_instance.show_estimated_total = True
#                 checkout_instance.show_related_products = True
#                 checkout_instance.show_social_sharing = False
#                 checkout_instance.thank_you_message = ''
#                 checkout_instance.show_terms_checkbox = True
#                 checkout_instance.terms_checkbox_text = 'I agree to the Terms & Conditions'
#                 checkout_instance.save()
#                 messages.success(
#                     request, "Checkout settings reset to defaults successfully.")
#                 logger.info(
#                     f"Checkout settings reset by user {request.user.id}"
#                 )
#             else:
#                 messages.warning(request, "No checkout settings to reset.")
#     except Exception as e:
#         logger.error(f"Error resetting checkout settings: {str(e)}")
#         messages.error(request, "Failed to reset checkout settings.")
#     return redirect('manage_checkout_settings')
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================

# logger = logging.getLogger(__name__)
@dashboard_prefix_required
def manage_cart_settings(request, prefix):
    """
    Manages the singleton CartSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.
    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing cart settings for this tenant
    cart_instance = CartSettings.objects.first()
    # Determine if this is create or edit mode
    is_create = cart_instance is None
    is_edit = cart_instance is not None
    # 2. Handle Form Submission
    if request.method == 'POST':
        form = CartSettingsForm(request.POST, instance=cart_instance)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()
                    messages.success(
                        request, "Cart settings updated successfully.")
                    logger.info(
                        f"Cart settings saved by user {request.user.id}"
                    )
                    # Redirect to same page to prevent resubmission
                    return redirect('manage_cart_settings')
            except Exception as e:
                logger.error(f"Error saving cart settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save cart settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = CartSettingsForm(instance=cart_instance)
    # 4. Prepare Context
    context = {
        'form': form,
        'object': cart_instance,
        'title': 'Cart Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }
    # 5. Add helper data for UI
    if cart_instance:
        # Count enabled cart features
        feature_count = sum([
            cart_instance.auto_open_on_add,
            cart_instance.show_continue_shopping,
            cart_instance.enable_cart_notes,
            cart_instance.show_product_images,
            cart_instance.show_variant_details,
            cart_instance.show_remove_button,
            cart_instance.enable_quantity_update,
            cart_instance.show_free_shipping_progress,
            cart_instance.show_discount_code_field,
            cart_instance.enable_cart_upsells,
            cart_instance.show_secure_checkout_badge,
            cart_instance.enable_cart_expiry,
        ])
        context['enabled_features_count'] = feature_count
        # Cart type display
        context['cart_type_display'] = cart_instance.get_cart_type_display()
        # Conversion optimization score (simple heuristic)
        conversion_score = 0
        if cart_instance.auto_open_on_add:
            conversion_score += 10
        if cart_instance.show_free_shipping_progress:
            conversion_score += 20
        if cart_instance.enable_cart_upsells:
            conversion_score += 20
        if cart_instance.show_discount_code_field:
            conversion_score += 10
        if cart_instance.show_secure_checkout_badge:
            conversion_score += 15
        if cart_instance.show_accepted_payments:
            conversion_score += 10
        if cart_instance.show_low_stock_warning:
            conversion_score += 15
        context['conversion_score'] = conversion_score
        # Drawer settings status
        context['drawer_enabled'] = cart_instance.cart_type == 'drawer'
        # Upsell configuration
        context['upsells_configured'] = (
            cart_instance.enable_cart_upsells and
            cart_instance.upsell_count > 0
        )
    return render(request, 'dashboard/store_settings/manage_cart_settings.html', context)


# # @dashboard_prefix_required
# def cart_preview(request,prefix):
#     """
#     Preview how the cart will appear with current settings.
#     Useful for testing cart type, drawer settings, and feature visibility.
#     """
#     cart_instance = CartSettings.objects.first()
#     if not cart_instance:
#         messages.warning(request, "Cart settings not configured yet.")
#         return redirect('manage_cart_settings')
#     context = {
#         'object': cart_instance,
#         'title': 'Cart Preview',
#     }
#     return render(request, 'cart/cart_preview.html', context)
# # @dashboard_prefix_required
# def reset_cart_settings(request,prefix):
#     """
#     Reset cart settings to default configuration.
#     """
#     cart_instance = CartSettings.objects.first()
#     try:
#         with transaction.atomic():
#             if cart_instance:
#                 # Reset to defaults
#                 cart_instance.cart_type = 'drawer'
#                 cart_instance.drawer_position = 'right'
#                 cart_instance.drawer_width = 400
#                 cart_instance.drawer_overlay_opacity = 50
#                 cart_instance.auto_open_on_add = True
#                 cart_instance.auto_close_delay = 0
#                 cart_instance.show_continue_shopping = True
#                 cart_instance.enable_cart_notes = True
#                 cart_instance.enable_gift_message = False
#                 cart_instance.enable_gift_wrapping = False
#                 cart_instance.gift_wrapping_price = Decimal('0.00')
#                 cart_instance.show_product_images = True
#                 cart_instance.image_size = 'medium'
#                 cart_instance.show_variant_details = True
#                 cart_instance.show_remove_button = True
#                 cart_instance.enable_quantity_update = True
#                 cart_instance.show_unit_price = True
#                 cart_instance.show_line_total = True
#                 cart_instance.show_item_subtotal = True
#                 cart_instance.show_savings = True
#                 cart_instance.show_tax_estimate = True
#                 cart_instance.show_shipping_estimate = True
#                 cart_instance.show_grand_total = True
#                 cart_instance.enable_cart_upsells = False
#                 cart_instance.upsell_title = 'Frequently Bought Together'
#                 cart_instance.upsell_count = 2
#                 cart_instance.upsell_algorithm = 'frequently_bought'
#                 cart_instance.show_free_shipping_progress = True
#                 cart_instance.free_shipping_threshold = Decimal('50.00')
#                 cart_instance.progress_bar_color = '#10B981'
#                 cart_instance.progress_message_below = 'Add {amount} more to get FREE shipping!'
#                 cart_instance.progress_message_reached = 'You qualify for FREE shipping!'
#                 cart_instance.show_discount_code_field = True
#                 cart_instance.discount_code_placeholder = 'Enter discount code'
#                 cart_instance.discount_code_position = 'bottom'
#                 cart_instance.checkout_button_text = 'Proceed to Checkout'
#                 cart_instance.checkout_button_style = 'full_width'
#                 cart_instance.show_secure_checkout_badge = True
#                 cart_instance.show_accepted_payments = True
#                 cart_instance.show_money_back_guarantee = False
#                 cart_instance.empty_cart_message = 'Your cart is empty'
#                 cart_instance.empty_cart_icon = 'shopping-cart'
#                 cart_instance.show_continue_shopping_on_empty = True
#                 cart_instance.show_popular_products_on_empty = True
#                 cart_instance.popular_products_count = 4
#                 cart_instance.enable_cart_expiry = True
#                 cart_instance.cart_expiry_days = 30
#                 cart_instance.show_expiry_warning = True
#                 cart_instance.show_low_stock_warning = True
#                 cart_instance.show_out_of_stock_warning = True
#                 cart_instance.auto_remove_out_of_stock = False
#                 cart_instance.save()
#                 messages.success(
#                     request, "Cart settings reset to defaults successfully.")
#                 logger.info(
#                     f"Cart settings reset by user {request.user.id}"
#                 )
#             else:
#                 messages.warning(request, "No cart settings to reset.")
#     except Exception as e:
#         logger.error(f"Error resetting cart settings: {str(e)}")
#         messages.error(request, "Failed to reset cart settings.")
#     return redirect('manage_cart_settings')
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# logger = logging.getLogger(__name__)
@dashboard_prefix_required
def manage_blog_settings(request, prefix):
    """
    Manages the singleton BlogSettings for the current tenant.
    Handles both Create (initial setup) and Update (editing) logic.
    Multi-Tenant Note:
    django-tenants middleware ensures this query only sees data
    within the current tenant's schema.
    """
    # 1. Retrieve the existing blog settings for this tenant
    blog_instance = BlogSettings.objects.first()
    # Determine if this is create or edit mode
    is_create = blog_instance is None
    is_edit = blog_instance is not None
    # 2. Handle Form Submission
    if request.method == 'POST':
        form = BlogSettingsForm(request.POST, instance=blog_instance)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the instance
                    saved_instance = form.save()
                    messages.success(
                        request, "Blog settings updated successfully.")
                    logger.info(
                        f"Blog settings saved by user {request.user.id}"
                    )
                    # Redirect to same page to prevent resubmission
                    return redirect('manage_blog_settings')
            except Exception as e:
                logger.error(f"Error saving blog settings: {str(e)}")
                messages.error(
                    request,
                    "Failed to save blog settings. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        # 3. Initial GET Request
        form = BlogSettingsForm(instance=blog_instance)
    # 4. Prepare Context
    context = {
        'form': form,
        'object': blog_instance,
        'title': 'Blog Settings',
        'action_url': request.path,
        'is_create': is_create,
        'is_edit': is_edit,
    }
    # 5. Add helper data for UI
    if blog_instance:
        # Count enabled blog features
        feature_count = sum([
            blog_instance.enable_blog,
            blog_instance.show_sidebar,
            blog_instance.show_featured_image,
            blog_instance.show_author,
            blog_instance.show_date,
            blog_instance.show_reading_time,
            blog_instance.show_excerpt,
            blog_instance.show_tags,
            blog_instance.show_categories,
            blog_instance.enable_comments,
            blog_instance.show_share_buttons,
            blog_instance.show_related_posts,
            blog_instance.auto_generate_meta,
            blog_instance.show_breadcrumbs,
            blog_instance.enable_schema_markup,
            blog_instance.enable_rss_feed,
        ])
        context['enabled_features_count'] = feature_count
        # Blog status
        context['blog_enabled'] = blog_instance.enable_blog
        context['layout_display'] = blog_instance.get_layout_display()
        # Comment system status
        context['comment_system_display'] = blog_instance.get_comment_system_display()
        context['comments_enabled'] = (
            blog_instance.enable_comments and
            blog_instance.comment_system != 'disabled'
        )
        # SEO score (simple heuristic)
        seo_score = 0
        if blog_instance.auto_generate_meta:
            seo_score += 25
        if blog_instance.show_breadcrumbs:
            seo_score += 25
        if blog_instance.enable_schema_markup:
            seo_score += 25
        if blog_instance.blog_description:
            seo_score += 25
        context['seo_score'] = seo_score
        # Widget count
        widget_count = sum([
            blog_instance.show_search_widget,
            blog_instance.show_categories_widget,
            blog_instance.show_recent_posts_widget,
            blog_instance.show_popular_posts_widget,
            blog_instance.show_tags_widget,
            blog_instance.show_newsletter_widget,
        ])
        context['enabled_widgets_count'] = widget_count
    return render(request, 'dashboard/store_settings/manage_blog_settings.html', context)


# # @dashboard_prefix_required
# def blog_preview(request,prefix):
#     """
#     Preview how the blog will appear with current settings.
#     Useful for testing layout, post display, and sidebar configuration.
#     """
#     blog_instance = BlogSettings.objects.first()
#     if not blog_instance:
#         messages.warning(request, "Blog settings not configured yet.")
#         return redirect('manage_blog_settings')
#     context = {
#         'object': blog_instance,
#         'title': 'Blog Preview',
#     }
#     return render(request, 'blog/blog_preview.html', context)
# # @dashboard_prefix_required
# def reset_blog_settings(request,prefix):
#     """
#     Reset blog settings to default configuration.
#     """
#     blog_instance = BlogSettings.objects.first()
#     try:
#         with transaction.atomic():
#             if blog_instance:
#                 # Reset to defaults
#                 blog_instance.enable_blog = True
#                 blog_instance.blog_title = 'Blog'
#                 blog_instance.blog_description = ''
#                 blog_instance.blog_url_prefix = 'blog'
#                 blog_instance.layout = 'grid'
#                 blog_instance.posts_per_page = 12
#                 blog_instance.posts_per_row = 3
#                 blog_instance.show_sidebar = True
#                 blog_instance.sidebar_position = 'right'
#                 blog_instance.show_featured_image = True
#                 blog_instance.featured_image_aspect_ratio = '16_9'
#                 blog_instance.show_author = True
#                 blog_instance.show_author_avatar = True
#                 blog_instance.show_date = True
#                 blog_instance.date_format = 'short'
#                 blog_instance.show_reading_time = True
#                 blog_instance.show_excerpt = True
#                 blog_instance.excerpt_length = 150
#                 blog_instance.show_read_more_button = True
#                 blog_instance.show_tags = True
#                 blog_instance.show_categories = True
#                 blog_instance.show_view_count = False
#                 blog_instance.show_author_bio = True
#                 blog_instance.show_share_buttons = True
#                 blog_instance.share_button_position = 'both'
#                 blog_instance.show_related_posts = True
#                 blog_instance.related_posts_count = 3
#                 blog_instance.show_post_navigation = True
#                 blog_instance.enable_comments = True
#                 blog_instance.comment_system = 'native'
#                 blog_instance.require_approval = True
#                 blog_instance.require_login_to_comment = False
#                 blog_instance.show_comment_count = True
#                 blog_instance.auto_generate_meta = True
#                 blog_instance.show_breadcrumbs = True
#                 blog_instance.enable_schema_markup = True
#                 blog_instance.show_search_widget = True
#                 blog_instance.show_categories_widget = True
#                 blog_instance.show_recent_posts_widget = True
#                 blog_instance.show_popular_posts_widget = True
#                 blog_instance.show_tags_widget = True
#                 blog_instance.show_newsletter_widget = True
#                 blog_instance.recent_posts_count = 5
#                 blog_instance.popular_posts_count = 5
#                 blog_instance.enable_rss_feed = True
#                 blog_instance.rss_posts_count = 20
#                 blog_instance.save()
#                 messages.success(
#                     request, "Blog settings reset to defaults successfully.")
#                 logger.info(
#                     f"Blog settings reset by user {request.user.id}"
#                 )
#             else:
#                 messages.warning(request, "No blog settings to reset.")
#     except Exception as e:
#         logger.error(f"Error resetting blog settings: {str(e)}")
#         messages.error(request, "Failed to reset blog settings.")
#     return redirect('manage_blog_settings')
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# logger = logging.getLogger(__name__)
# # @dashboard_prefix_required
# def banner_slide_list(request,prefix):
#     """
#     List all banner slides with filtering and reordering.
#     Shows slide status, date range, and display order.
#     """
#     # Get all slides for this tenant (django-tenants handles schema isolation)
#     slides = BannerSlide.objects.all()
#     # Filtering
#     status_filter = request.GET.get('status', '')
#     date_filter = request.GET.get('date', '')
#     search_query = request.GET.get('search', '')
#     if status_filter == 'active':
#         slides = slides.filter(is_active=True)
#     elif status_filter == 'inactive':
#         slides = slides.filter(is_active=False)
#     if date_filter == 'current':
#         now = timezone.now()
#         slides = slides.filter(
#             Q(start_date__isnull=True) | Q(start_date__lte=now),
#             Q(end_date__isnull=True) | Q(end_date__gte=now)
#         )
#     elif date_filter == 'scheduled':
#         slides = slides.filter(start_date__gt=timezone.now())
#     elif date_filter == 'expired':
#         slides = slides.filter(end_date__lt=timezone.now())
#     if search_query:
#         slides = slides.filter(
#             Q(title__icontains=search_query) |
#             Q(subtitle__icontains=search_query) |
#             Q(cta_text__icontains=search_query)
#         )
#     # Get counts for filter badges
#     status_counts = {
#         'active': slides.filter(is_active=True).count(),
#         'inactive': slides.filter(is_active=False).count(),
#         'current': slides.filter(
#             Q(start_date__isnull=True) | Q(start_date__lte=timezone.now()),
#             Q(end_date__isnull=True) | Q(end_date__gte=timezone.now())
#         ).count(),
#     }
#     # Get counts for bulk action form
#     total_count = slides.count()
#     context = {
#         'slides': slides,
#         'status_counts': status_counts,
#         'total_count': total_count,
#         'current_status': status_filter,
#         'current_date': date_filter,
#         'search_query': search_query,
#         'title': 'Banner Slides',
#         'bulk_form': BannerSlideBulkActionForm(),
#     }
#     return render(request, 'banners/banner_slide_list.html', context)

@dashboard_prefix_required
def banner_slide_create(request, prefix):
    """
    Create a new banner slide.
    """
    if request.method == 'POST':
        form = BannerSlideForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    slide = form.save()
                    messages.success(
                        request,
                        f"Banner slide '{slide.title}' created successfully."
                    )
                    logger.info(
                        f"BannerSlide created by user {request.user.id}: {slide.title}"
                    )
                    return redirect('banner_slide_edit', pk=slide.pk)
            except Exception as e:
                logger.error(f"Error creating banner slide: {str(e)}")
                messages.error(
                    request,
                    "Failed to create banner slide. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        form = BannerSlideForm()
    context = {
        'form': form,
        'title': 'Create Banner Slide',
        'action_url': request.path,
        'is_create': True,
    }
    return render(request, 'dashboard/store_settings/banner_slide_form.html', context)


@dashboard_prefix_required
def banner_slide_edit(request, prefix, pk):
    """
    Edit an existing banner slide.
    """
    slide = get_object_or_404(BannerSlide, pk=pk)
    if request.method == 'POST':
        form = BannerSlideForm(request.POST, request.FILES, instance=slide)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    messages.success(
                        request,
                        f"Banner slide '{slide.title}' updated successfully."
                    )
                    logger.info(
                        f"BannerSlide updated by user {request.user.id}: {slide.title}"
                    )
                    return redirect('banner_slide_list')
            except Exception as e:
                logger.error(f"Error updating banner slide: {str(e)}")
                messages.error(
                    request,
                    "Failed to update banner slide. Please try again."
                )
        else:
            messages.error(request, "Please correct the errors below.")
            logger.warning(
                f"Form validation failed for user {request.user.id}: {form.errors}"
            )
    else:
        form = BannerSlideForm(instance=slide)
    context = {
        'form': form,
        'object': slide,
        'title': f'Edit Banner: {slide.title}',
        'action_url': request.path,
        'is_edit': True,
    }
    return render(request, 'dashboard/store_settings/banner_slide_form.html', context)


# # @dashboard_prefix_required
# def banner_slide_delete(request, pk):
#     """
#     Delete a banner slide.
#     """
#     slide = get_object_or_404(BannerSlide, pk=pk)
#     slide_title = slide.title
#     try:
#         with transaction.atomic():
#             slide.delete()
#             messages.success(
#                 request,
#                 f"Banner slide '{slide_title}' deleted successfully."
#             )
#             logger.info(
#                 f"BannerSlide deleted by user {request.user.id}: {slide_title}"
#             )
#     except Exception as e:
#         logger.error(f"Error deleting banner slide: {str(e)}")
#         messages.error(request, "Failed to delete banner slide.")
#     return redirect('banner_slide_list')
# # @dashboard_prefix_required
# def banner_slide_duplicate(request, pk):
#     """
#     Duplicate an existing banner slide as a starting point for new campaigns.
#     """
#     original = get_object_or_404(BannerSlide, pk=pk)
#     try:
#         with transaction.atomic():
#             # Create a copy with modified title
#             slide = BannerSlide.objects.create(
#                 title=f"{original.title} (Copy)",
#                 subtitle=original.subtitle,
#                 description=original.description,
#                 image_desktop=original.image_desktop,
#                 image_mobile=original.image_mobile,
#                 text_position=original.text_position,
#                 text_color=original.text_color,
#                 overlay_opacity=original.overlay_opacity,
#                 cta_text=original.cta_text,
#                 cta_link=original.cta_link,
#                 cta_style=original.cta_style,
#                 show_cta=original.show_cta,
#                 is_active=False,  # Always start as inactive
#                 display_order=original.display_order + 1,
#                 start_date=original.start_date,
#                 end_date=original.end_date,
#             )
#             messages.success(
#                 request,
#                 f"Banner slide '{original.title}' duplicated as '{slide.title}'."
#             )
#             logger.info(
#                 f"BannerSlide duplicated: {original.title} -> {slide.title}"
#             )
#             return redirect('banner_slide_edit', pk=slide.pk)
#     except Exception as e:
#         logger.error(f"Error duplicating banner slide: {str(e)}")
#         messages.error(request, "Failed to duplicate banner slide.")
#         return redirect('banner_slide_list')
# # @dashboard_prefix_required
# def banner_slide_preview(request, pk):
#     """
#     Preview how a banner slide will appear on the homepage.
#     """
#     slide = get_object_or_404(BannerSlide, pk=pk)
#     context = {
#         'object': slide,
#         'title': f'Preview Banner: {slide.title}',
#     }
#     return render(request, 'banners/banner_slide_preview.html', context)
# # @dashboard_prefix_required
# def banner_slide_bulk_action(request,prefix):
#     """
#     Perform bulk actions on multiple banner slides.
#     Expects POST with action and slide_ids.
#     """
#     if request.method != 'POST':
#         return redirect('banner_slide_list')
#     form = BannerSlideBulkActionForm(request.POST)
#     if form.is_valid():
#         action = form.cleaned_data.get('action')
#         slide_ids = request.POST.getlist('slide_ids')
#         if not slide_ids:
#             messages.warning(request, "No banner slides selected.")
#             return redirect('banner_slide_list')
#         try:
#             with transaction.atomic():
#                 slides = BannerSlide.objects.filter(pk__in=slide_ids)
#                 count = slides.count()
#                 if action == 'activate':
#                     slides.update(is_active=True)
#                     messages.success(request, f"{count} slide(s) activated.")
#                 elif action == 'deactivate':
#                     slides.update(is_active=False)
#                     messages.success(request, f"{count} slide(s) deactivated.")
#                 elif action == 'delete':
#                     slides.delete()
#                     messages.success(request, f"{count} slide(s) deleted.")
#                 logger.info(
#                     f"Bulk action '{action}' performed on {count} banner slides by user {request.user.id}"
#                 )
#         except Exception as e:
#             logger.error(f"Error performing bulk action: {str(e)}")
#             messages.error(request, "Failed to perform bulk action.")
#     else:
#         messages.error(request, "Invalid action.")
#     return redirect('banner_slide_list')
# # @dashboard_prefix_required
# def banner_slide_reorder(request,prefix):
#     """
#     AJAX endpoint for reordering banner slides via drag-and-drop.
#     Expects JSON with slide IDs in new order.
#     """
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Method not allowed'}, status=405)
#     import json
#     try:
#         data = json.loads(request.body)
#         slide_ids = data.get('slide_ids', [])
#         with transaction.atomic():
#             for order, slide_id in enumerate(slide_ids):
#                 BannerSlide.objects.filter(
#                     pk=slide_id).update(display_order=order)
#         logger.info(
#             f"Banner slides reordered by user {request.user.id}"
#         )
#         return JsonResponse({'success': True, 'message': 'Slides reordered successfully.'})
#     except Exception as e:
#         logger.error(f"Error reordering banner slides: {str(e)}")
#         return JsonResponse({'error': str(e)}, status=500)
# # @dashboard_prefix_required
# def banner_slide_stats(request,prefix):
#     """
#     Get banner slide statistics for dashboard widgets.
#     Returns JSON data.
#     """
#     now = timezone.now()
#     stats = {
#         'total': BannerSlide.objects.count(),
#         'active': BannerSlide.objects.filter(is_active=True).count(),
#         'inactive': BannerSlide.objects.filter(is_active=False).count(),
#         'current': BannerSlide.objects.filter(
#             Q(start_date__isnull=True) | Q(start_date__lte=now),
#             Q(end_date__isnull=True) | Q(end_date__gte=now)
#         ).count(),
#         'scheduled': BannerSlide.objects.filter(start_date__gt=now).count(),
#         'expired': BannerSlide.objects.filter(end_date__lt=now).count(),
#     }
#     return JsonResponse(stats)
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
# # ==========================================================================================================================================================================
