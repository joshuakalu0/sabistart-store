from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
from django.urls import reverse
from dashboard.feature_marketplace.services import FeatureEntitlementEngine, QuotaExceededError, enforce_quota
from public.product.models import (
    AttributeGroup, Attribute, AttributeValue, Product, ProductImage,
    ProductVideo, ProductAttributeValue, ProductVariant, VariantImage
)
from .forms import ProductForm, ProductImageForm, ProductImageFormSet, AttributeGroupForm, AttributeForm, AttributeValueForm
from dashboard.decorators import dashboard_prefix_required
import json
from dashboard.sidebar_utiles import main_sidebar, get_settings_sidebar, get_sidebar_with_active, get_sub_sidebar_with_active
from .te import (
    ProductCreationForm,
)

from public.product.models import (
    Product, ProductImage,
    Attribute, AttributeValue, AttributeGroup,
    Category, Tag, Brand
)

from .utiles import cast_matching_keys

# ============================================================================
# CUSTOM JSON ENCODER
# ============================================================================


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal, UUID, and other special types"""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, timezone.datetime):
            return obj.isoformat()
        if isinstance(obj, timezone.date):
            return obj.isoformat()
        if hasattr(obj, 'url'):
            return obj.url if obj else None
        return super().default(obj)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def clean_post_lists(request, fields):
    """
    Remove fields from request.POST if their value is [''].

    Args:
        request: Django request object
        fields: list of field names to check (e.g. ['tags', 'categories'])

    Returns:
        cleaned QueryDict
    """
    data = request.POST.copy()

    for field in fields:
        values = data.getlist(field)

        if values == ['']:
            data.pop(field, None)

    return data


def serialize_attribute(attribute):
    """Serialize an Attribute object for JavaScript"""
    attr_data = {
        'id': str(attribute.id),
        'name': attribute.name,
        'slug': attribute.slug,
        'attribute_type': attribute.attribute_type,
        'unit': attribute.unit or '',
        'help_text': attribute.help_text or '',
        'description': attribute.description or '',
        'min_value': float(attribute.min_value) if attribute.min_value else None,
        'max_value': float(attribute.max_value) if attribute.max_value else None,
        'is_required': attribute.is_required,
        'is_variant_option': attribute.is_variant_option,
        'display_order': attribute.display_order,
        'values': []
    }

    # Serialize attribute values
    for value in attribute.values.filter(is_active=True).order_by('display_order', 'value'):
        attr_data['values'].append({
            'id': str(value.id),
            'value': value.value,
            'slug': value.slug,
            'color_hex': value.color_hex or '',
            'extra_price': float(value.extra_price) if value.extra_price else 0,
            'image_url': value.image.url if value.image else None,
            'swatch_url': value.swatch.url if value.swatch else None,
            'description': value.description or '',
            'display_order': value.display_order,
        })

    return attr_data


def serialize_variant(variant):
    """Serialize a ProductVariant object for JavaScript"""
    variant_data = {
        'id': str(variant.id),
        'sku': variant.sku,
        'barcode': variant.barcode or '',
        'mpn': variant.mpn or '',
        'gtin': variant.gtin or '',
        'variant_name': variant.variant_name or '',
        'price': float(variant.price) if variant.price else 0,
        'compare_at_price': float(variant.compare_at_price) if variant.compare_at_price else None,
        'cost_price': float(variant.cost_price) if variant.cost_price else None,
        'stock_quantity': variant.stock_quantity,
        'reserved_quantity': variant.reserved_quantity,
        'available_quantity': variant.available_quantity,
        'low_stock_threshold': variant.low_stock_threshold,
        'weight': float(variant.weight) if variant.weight else None,
        'length': float(variant.length) if variant.length else None,
        'width': float(variant.width) if variant.width else None,
        'height': float(variant.height) if variant.height else None,
        'is_active': variant.is_active,
        'is_default': variant.is_default,
        'sales_count': variant.sales_count,
        'options': []
    }

    # Serialize variant option values
    for option_value in variant.option_values.all():
        variant_data['options'].append({
            'attributeId': str(option_value.attribute.id),
            'attributeName': option_value.attribute.name,
            'valueId': str(option_value.id),
            'value': option_value.value,
            'slug': option_value.slug,
        })

    return variant_data


def get_variant_capable_attributes():
    """Get all attributes that can be used for variants"""
    return Attribute.objects.filter(
        # is_active=True,
        is_variant_option=True
    ).prefetch_related(
        Prefetch('values', queryset=AttributeValue.objects.filter(
            is_active=True).order_by('display_order', 'value'))
    ).order_by('display_order', 'name')
# ====================================================================================


@login_required
@dashboard_prefix_required
def attribute_group_list(request, prefix):
    """Attribute group list page - requires valid prefix."""
    search_query = request.GET.get('search', '')
    groups = AttributeGroup.objects.all()

    if search_query:
        groups = groups.filter(Q(name__icontains=search_query) | Q(
            description__icontains=search_query))

    paginator = Paginator(groups, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'prefix': prefix,
        'page_title': 'Attribute Groups',
        'active_menu': 'attribute_groups',
        'store_name': 'My Store',
        'page_obj': page_obj,
        'search_query': search_query,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None
    }
    return render(request, 'dashboard/products/attribute_groups/list.html', context)


@login_required
@dashboard_prefix_required
def attribute_group_create(request, prefix):
    """Attribute group create page - requires valid prefix."""
    if request.method == 'POST':
        form = AttributeGroupForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    group = form.save()
                    messages.success(
                        request, f'Attribute group "{group.name}" created successfully.')
                    return redirect(reverse('dashboard:product_settings:attribute_group_list', args=[prefix]))
            except Exception as e:
                messages.error(
                    request, f'Error creating attribute group: {str(e)}')
    else:
        form = AttributeGroupForm()

    context = {
        'prefix': prefix,
        'page_title': 'Create Attribute Group',
        'active_menu': 'attribute_groups',
        'store_name': 'My Store',
        'form': form,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None
    }
    return render(request, 'dashboard/products/attribute_groups/create.html', context)


@login_required
@dashboard_prefix_required
def attribute_group_edit(request, prefix, pk):
    """Attribute group edit page - requires valid prefix."""
    group = get_object_or_404(AttributeGroup, pk=pk)

    if request.method == 'POST':
        form = AttributeGroupForm(request.POST, instance=group)
        if form.is_valid():
            try:
                with transaction.atomic():
                    group = form.save()
                    messages.success(
                        request, f'Attribute group "{group.name}" updated successfully.')
                    return redirect(reverse('dashboard:product_settings:attribute_group_list', args=[prefix]))
            except Exception as e:
                messages.error(
                    request, f'Error updating attribute group: {str(e)}')
    else:
        form = AttributeGroupForm(instance=group)

    context = {
        'prefix': prefix,
        'page_title': f'Edit {group.name}',
        'active_menu': 'attribute_groups',
        'store_name': 'My Store',
        'form': form,
        'group': group,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None
    }
    return render(request, 'dashboard/products/attribute_groups/edit.html', context)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def attribute_group_delete(request, prefix, pk):
    """Attribute group delete endpoint - requires valid prefix."""
    group = get_object_or_404(AttributeGroup, pk=pk)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                group_name = group.name
                group.delete()
                messages.success(
                    request, f'Attribute group "{group_name}" deleted successfully.')
        except Exception as e:
            messages.error(
                request, f'Error deleting attribute group: {str(e)}')

    return redirect(reverse('dashboard:product_settings:attribute_group_list', args=[prefix]))


@login_required
@dashboard_prefix_required
def attribute_list(request, prefix):
    """Attribute list page - requires valid prefix."""
    search_query = request.GET.get('search', '')
    group_filter = request.GET.get('group', '')
    type_filter = request.GET.get('type', '')

    attributes = Attribute.objects.select_related(
        'group').prefetch_related('values')

    if search_query:
        attributes = attributes.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query))
    if group_filter:
        attributes = attributes.filter(group_id=group_filter)
    if type_filter:
        attributes = attributes.filter(attribute_type=type_filter)

    paginator = Paginator(attributes, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    choice_types = ["select", "multiselect", "color"]

    context = {
        'prefix': prefix,
        'page_title': 'Attributes',
        'active_menu': 'attributes',
        'store_name': 'My Store',
        'page_obj': page_obj,
        'search_query': search_query,
        'group_filter': group_filter,
        'type_filter': type_filter,
        'groups': AttributeGroup.objects.all(),
        'types': Attribute.TYPE_CHOICES,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None,
        'choice_types': choice_types
    }
    return render(request, 'dashboard/products/attributes/list.html', context)


@login_required
@dashboard_prefix_required
def attribute_create(request, prefix):
    """Attribute create page - requires valid prefix."""
    if request.method == 'POST':
        form = AttributeForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    attribute = form.save()
                    messages.success(
                        request, f'Attribute "{attribute.name}" created successfully.')
                    return redirect(reverse('dashboard:product_settings:attribute_list', args=[prefix]))
            except Exception as e:
                messages.error(request, f'Error creating attribute: {str(e)}')
    else:
        form = AttributeForm()

    context = {
        'prefix': prefix,
        'page_title': 'Create Attribute',
        'active_menu': 'attributes',
        'store_name': 'My Store',
        'form': form,
        'attribute': None,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None
    }
    return render(request, 'dashboard/products/attributes/create.html', context)


@login_required
@dashboard_prefix_required
def attribute_edit(request, prefix, pk):
    """Attribute edit page - requires valid prefix."""
    attribute = get_object_or_404(Attribute, pk=pk)

    if request.method == 'POST':
        form = AttributeForm(request.POST, instance=attribute)
        if form.is_valid():
            try:
                with transaction.atomic():
                    attribute = form.save()
                    messages.success(
                        request, f'Attribute "{attribute.name}" updated successfully.')
                    return redirect(reverse('dashboard:product_settings:attribute_list', args=[prefix]))
            except Exception as e:
                messages.error(request, f'Error updating attribute: {str(e)}')
    else:
        form = AttributeForm(instance=attribute)

    context = {
        'prefix': prefix,
        'page_title': f'Edit {attribute.name}',
        'active_menu': 'attributes',
        'store_name': 'My Store',
        'form': form,
        'attribute': attribute,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None
    }
    return render(request, 'dashboard/products/attributes/create.html', context)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def attribute_delete(request, prefix, pk):
    """Attribute delete endpoint - requires valid prefix."""
    attribute = get_object_or_404(Attribute, pk=pk)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                attribute_name = attribute.name
                attribute.delete()
                messages.success(
                    request, f'Attribute "{attribute_name}" deleted successfully.')
        except Exception as e:
            messages.error(request, f'Error deleting attribute: {str(e)}')

    return redirect(reverse('dashboard:product_settings:attribute_list', args=[prefix]))


@login_required
@dashboard_prefix_required
def attribute_value_list(request, prefix, attribute_id):
    """Attribute value list page - requires valid prefix."""
    attribute = get_object_or_404(Attribute, pk=attribute_id)
    search_query = request.GET.get('search', '')
    values = AttributeValue.objects.filter(attribute=attribute)

    if search_query:
        values = values.filter(Q(value__icontains=search_query) | Q(
            description__icontains=search_query))

    paginator = Paginator(values, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'prefix': prefix,
        'page_title': f'Values for {attribute.name}',
        'active_menu': 'attributes',
        'store_name': 'My Store',
        'page_obj': page_obj,
        'search_query': search_query,
        'attribute': attribute,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None
    }
    return render(request, 'dashboard/products/attribute_values/list.html', context)


@login_required
@dashboard_prefix_required
def attribute_value_create(request, prefix, attribute_id):
    """Attribute value create page - requires valid prefix."""
    attribute = get_object_or_404(Attribute, pk=attribute_id)
    print(request.POST)

    if request.method == 'POST':
        form = AttributeValueForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    value = form.save(commit=False)
                    value.attribute = attribute
                    # Set active status based on save status
                    save_status = request.POST.get('save_status', 'active')
                    value.is_active = save_status == 'active'
                    value.save()
                    messages.success(
                        request, f'Value "{value.value}" created successfully.')
                    return redirect(reverse('dashboard:product_settings:attribute_value_list', args=[prefix, attribute_id]))
            except Exception as e:
                messages.error(request, f'Error creating value: {str(e)}')
        else:
            print(form.errors, '=============')
    else:
        form = AttributeValueForm(initial={'attribute': attribute})

    choice_types = ["image", "color"]

    context = {
        'prefix': prefix,
        'page_title': f'Create Value for {attribute.name}',
        'active_menu': 'attributes',
        'store_name': 'My Store',
        'form': form,
        'attribute': attribute,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None,
        'choice_types': choice_types
    }
    return render(request, 'dashboard/products/attribute_values/create.html', context)


@login_required
@dashboard_prefix_required
def attribute_value_edit(request, prefix, pk):
    """Attribute value edit page - requires valid prefix."""
    value = get_object_or_404(AttributeValue, pk=pk)

    if request.method == 'POST':
        form = AttributeValueForm(request.POST, request.FILES, instance=value)
        if form.is_valid():
            try:
                with transaction.atomic():
                    value = form.save(commit=False)
                    # Set active status based on save status
                    save_status = request.POST.get('save_status', 'active')
                    value.is_active = save_status == 'active'
                    value.save()
                    messages.success(
                        request, f'Value "{value.value}" updated successfully.')
                    return redirect(reverse('dashboard:product_settings:attribute_value_list', args=[prefix, value.attribute.id]))
            except Exception as e:
                messages.error(request, f'Error updating value: {str(e)}')
        else:
            print(form.error, '=============')
    else:
        form = AttributeValueForm(instance=value)

    context = {
        'prefix': prefix,
        'page_title': f'Edit Value: {value.value}',
        'active_menu': 'attributes',
        'store_name': 'My Store',
        'form': form,
        'value': value,
        'sidebar': main_sidebar(prefix),
        'sub_sidebar': None
    }
    return render(request, 'dashboard/products/attribute_values/edit.html', context)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def attribute_value_delete(request, prefix, pk):
    """Attribute value delete endpoint - requires valid prefix."""
    value = get_object_or_404(AttributeValue, pk=pk)
    attribute_id = value.attribute.id

    if request.method == 'POST':
        try:
            with transaction.atomic():
                value_name = value.value
                value.delete()
                messages.success(
                    request, f'Value "{value_name}" deleted successfully.')
        except Exception as e:
            messages.error(request, f'Error deleting value: {str(e)}')

    return redirect(reverse('dashboard:product_settings:attribute_value_list', args=[prefix, attribute_id]))


@login_required
@dashboard_prefix_required
@require_http_methods(["GET"])
def product_details(request, prefix, pk):
    """Product details endpoint for modal - requires valid prefix."""
    product = get_object_or_404(Product, pk=pk)

    # Render product details HTML snippet
    context = {"product": product}
    return render(request, "dashboard/products/partials/details.html", context)


@login_required
@dashboard_prefix_required
@require_http_methods(["GET"])
def attribute_details(request, prefix, pk):
    """Attribute details endpoint for modal - requires valid prefix."""
    attribute = get_object_or_404(Attribute, pk=pk)

    # Render attribute details HTML snippet
    context = {"attribute": attribute}
    return render(request, "dashboard/products/attributes/partials/details.html", context)


@login_required
@dashboard_prefix_required
@require_http_methods(["GET"])
def attribute_group_details(request, prefix, pk):
    """Attribute group details endpoint for modal - requires valid prefix."""
    group = get_object_or_404(AttributeGroup, pk=pk)

    # Render attribute group details HTML snippet
    context = {"group": group}
    return render(request, "dashboard/products/attribute_groups/partials/details.html", context)


@login_required
@dashboard_prefix_required
@require_http_methods(["GET"])
def attribute_value_details(request, prefix, pk):
    """Attribute value details endpoint for modal - requires valid prefix."""
    value = get_object_or_404(AttributeValue, pk=pk)

    # Render attribute value details HTML snippet
    context = {"value": value}
    return render(request, "dashboard/products/attribute_values/partials/details.html", context)


@login_required
@dashboard_prefix_required
def product_list(request, prefix):
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')

    products = Product.objects.select_related(
        'brand').prefetch_related('categories', 'tags')
    print(products)

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | Q(sku__icontains=search_query))
    if status_filter:
        products = products.filter(status=status_filter)
    if type_filter:
        products = products.filter(product_type=type_filter)

    paginator = Paginator(products, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    from public.category.models import Category, Brand
    context = {
        'page_obj': page_obj, 'search_query': search_query, 'status_filter': status_filter,
        'type_filter': type_filter, 'categories': Category.objects.all(), 'brands': Brand.objects.all(),
        'statuses': Product._meta.get_field('status').choices, 'types': Product.TYPE_CHOICES, 'sidebar': main_sidebar(prefix),
        'sub_sidebar': None,
        'prefix': prefix, 'title': 'Products'
    }

    return render(request, 'dashboard/products/list.html', context=context)


def product_create(request, prefix):
    """
    Create new product with all related forms and formsets
    Shares template with product_edit
    """
    # Get all variant-capable attributes
    available_attributes = get_variant_capable_attributes()

    # Serialize attributes for JavaScript
    available_attributes_data = [serialize_attribute(
        attr) for attr in available_attributes]
    attribute_groups = AttributeGroup.objects.all().order_by('display_order')
    # print(request.POST)

    if request.method == 'POST':
        # print("POST data received:", dict(request.POST))
        # print('=============', request.POST, '<<<<<')
        p_type = request.POST.get('product_type')
        p_status = request.POST.get('status')
        post_data = clean_post_lists(request, ['categories', 'tags'])

        form = ProductCreationForm(
            data=post_data, files=request.FILES)

        is_valid = form.is_valid()
        print("Form validation result:", is_valid)
        if not is_valid:
            pass
            # print("Form errors:", form.errors)
            # # Debug individual form validation
            # print("Basic form valid:", form.basic_form.is_valid())
            # print("Basic form errors:", form.basic_form.errors)
            # print("Pricing form valid:", form.pricing_form.is_valid())
            # print("Pricing form errors:", form.pricing_form.errors)
            # print("Inventory form valid:", form.inventory_form.is_valid())
            # print("Inventory form errors:", form.inventory_form.errors)
            # print("Shipping form valid:", form.shipping_form.is_valid())
            # print("Shipping form errors:", form.shipping_form.errors)
            # print("Digital form valid:", form.digital_form.is_valid())
            # print("Digital form errors:", form.digital_form.errors)
            # print("Subscription form valid:",
            #       form.subscription_form.is_valid())
            # print("Subscription form errors:", form.subscription_form.errors)
            # print("SEO form valid:", form.seo_form.is_valid())
            # print("SEO form errors:", form.seo_form.errors)
            # print("Visibility form valid:", form.visibility_form.is_valid())
            # print("Visibility form errors:", form.visibility_form.errors)
            # print("Purchase form valid:", form.purchase_form.is_valid())
            # print("Purchase form errors:", form.purchase_form.errors)
            # print("Image formset valid:", form.image_formset.is_valid())
            # print("Image formset errors:", form.image_formset.errors)
            # print("Video formset valid:", form.video_formset.is_valid())
            # print("Video formset errors:", form.video_formset.errors)
            print("Attribute formset valid:",
                  form.attribute_formset.is_valid())
            print("Attribute formset errors:", form.attribute_formset.errors)
            print("Variant formset valid:", form.variant_formset.is_valid())
            print("Variant formset errors:", form.variant_formset.errors)

        if is_valid:
            try:
                with transaction.atomic():
                    enforce_quota("max_products")
                    # Save product
                    product = form.save(commit=True)

                    # Handle specifications data
                    specifications_data = request.POST.get(
                        'specifications', '')
                    if specifications_data:
                        try:
                            product.specifications = json.loads(
                                specifications_data)
                        except json.JSONDecodeError:
                            product.specifications = {}

                    # Handle features data
                    features_data = request.POST.get('features', '')
                    if features_data:
                        try:
                            product.features = json.loads(features_data)
                        except json.JSONDecodeError:
                            product.features = []

                    # Save the updated product with specifications and features
                    product.save()

                    # Handle uploaded images
                    uploaded_images = request.FILES.getlist('images')
                    for i, image_file in enumerate(uploaded_images):
                        ProductImage.objects.create(
                            product=product,
                            image=image_file,
                            caption=image_file.name,
                            is_primary=(i == 0),
                            display_order=i
                        )

                    # Log creation
                    FeatureEntitlementEngine().rebuild_quota("max_products")
                    messages.success(
                        request,
                        f'Product "{product.name}" created successfully! '
                        f'<a href="#" '
                        # f'<a href="{reverse('dashboard:product_settings:edit', kwargs={"pk": product.pk, 'prefix': prefix})}" '
                        f'class="font-medium text-primary-600 hover:text-primary-500">Edit Product</a>'
                    )

                    return redirect('dashboard:product_settings:product_list', prefix=prefix)

            except Exception as e:
                print(e, '=======')
                messages.error(request, f'Error creating product: {str(e)}')
        else:
            errors = {}
            if form.errors:
                errors.update(form.errors)

            print('Please correct the errors below.', errors)
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductCreationForm()

    # Get filter data for forms
    categories = Category.objects.filter(is_active=True).order_by('name')
    brands = Brand.objects.filter(is_active=True).order_by('name')
    tags = Tag.objects.filter(is_active=True).order_by('name')
    attributes = Attribute.objects.filter(
        is_variant_option=True).order_by('name')
    # attributes = Attribute.objects.filter(
    #     is_active=True, is_variant_option=True).order_by('name')

    # Serialize data for JavaScript
    categories_json = json.dumps(
        [{'id': str(cat.id), 'name': cat.name, 'parent_id': cat.parent_id} for cat in categories])
    tags_json = json.dumps(
        [{'id': str(tag.id), 'name': tag.name} for tag in tags])
    attributes_json = json.dumps([{
        'id': str(attr.id),
        'name': attr.name,
        'slug': attr.slug,
        'type': attr.attribute_type,
        'values': [{
            'id': str(value.id),
            'value': value.value,
            'slug': value.slug,
            'color_hex': value.color_hex
        } for value in attr.values.all()]
    } for attr in attributes])

    context = {
        'form': form,
        'categories': categories,
        'categories_json': categories_json,
        'brands': brands,
        'tags': tags_json,
        'attributes': attributes,
        'is_edit': False,
        'prefix': prefix,
        'attribute_groups': attribute_groups,
        'available_attributes': available_attributes,
        'available_attributes_json': json.dumps(available_attributes_data, cls=DecimalEncoder),
        'existing_variants_json': json.dumps([], cls=DecimalEncoder),
        'PRODUCT_TYPE_CHOICES': Product.TYPE_CHOICES,
        'sidebar': main_sidebar(prefix),
    }
    # dashboard/products/attributes/form.html

    return render(request, 'dashboard/products/product_form.html', context)


def product_edit(request, prefix, pk):
    """
    Create new product with all related forms and formsets
    Shares template with product_edit
    """

    product = get_object_or_404(
        Product.objects.prefetch_related(
            'images',
            'videos',
            'attribute_values__attribute',
            'variants__option_values',
        ),
        pk=pk,
    )
    # Get all variant-capable attributes
    available_attributes = get_variant_capable_attributes()

    # Serialize attributes for JavaScript
    available_attributes_data = [serialize_attribute(
        attr) for attr in available_attributes]
    attribute_groups = AttributeGroup.objects.all().order_by('display_order')
    # print(request.POST)

    if request.method == 'POST':

        # da = cast_matching_keys(
        #     data=request.POST, endswith=True, match='option_values', inplace=True)
        # print("Raw Files:>>>>>", da)

        # print("POST data received:", dict(request.POST))
        # print('=============', request.POST, '<<<<<')
        p_type = request.POST.get('product_type')
        p_status = request.POST.get('status')
        post_data = clean_post_lists(request, ['categories', 'tags'])
        post_data = cast_matching_keys(
            data=post_data, endswith='option_values', inplace=False, wanted_type='list')
        print(post_data)

        form = ProductCreationForm(
            data=post_data, files=request.FILES, instance=product,)

        print("Form validation result:", form.is_valid())
        if not form.is_valid():
            pass
            # print("Form errors:", form.errors)
            # # Debug individual form validation
            # print("Basic form valid:", form.basic_form.is_valid())
            # print("Basic form errors:", form.basic_form.errors)
            # print("Pricing form valid:", form.pricing_form.is_valid())
            # print("Pricing form errors:", form.pricing_form.errors)
            # print("Inventory form valid:", form.inventory_form.is_valid())
            # print("Inventory form errors:", form.inventory_form.errors)
            # print("Shipping form valid:", form.shipping_form.is_valid())
            # print("Shipping form errors:", form.shipping_form.errors)
            # print("Digital form valid:", form.digital_form.is_valid())
            # print("Digital form errors:", form.digital_form.errors)
            # print("Subscription form valid:",
            #       form.subscription_form.is_valid())
            # print("Subscription form errors:", form.subscription_form.errors)
            # print("SEO form valid:", form.seo_form.is_valid())
            # print("SEO form errors:", form.seo_form.errors)
            # print("Visibility form valid:", form.visibility_form.is_valid())
            # print("Visibility form errors:", form.visibility_form.errors)
            # print("Purchase form valid:", form.purchase_form.is_valid())
            # print("Purchase form errors:", form.purchase_form.errors)
            # print("Image formset valid:", form.image_formset.is_valid())
            # print("Image formset errors:", form.image_formset.errors)
            # print("Video formset valid:", form.video_formset.is_valid())
            # print("Video formset errors:", form.video_formset.errors)
            print("Attribute formset valid:",
                  form.attribute_formset.is_valid())
            print("Attribute formset errors:", form.attribute_formset.errors)
            print("Variant formset valid:", form.variant_formset.is_valid())
            print("Variant formset errors:", form.variant_formset.errors)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save product
                    product = form.save(commit=True)

                    # Handle specifications data
                    specifications_data = post_data.get('specifications', '')
                    if specifications_data:
                        product.specifications = specifications_data

                    # Handle features data
                    features_data = post_data.get('features', '')
                    if features_data:
                        product.features = features_data

                    # Save the updated product with specifications and features
                    product.save()

                    # Handle uploaded images
                    uploaded_images = request.FILES.getlist('images')
                    for i, image_file in enumerate(uploaded_images):
                        ProductImage.objects.create(
                            product=product,
                            image=image_file,
                            caption=image_file.name,
                            is_primary=(i == 0),
                            display_order=i
                        )

                    # Log creation
                    messages.success(
                        request,
                        f'Product "{product.name}" created successfully! '
                        # f'<a href="{reverse('dashboard:product_settings:edit', kwargs={"pk": product.pk, 'prefix': prefix})}" '
                        f'class="font-medium text-primary-600 hover:text-primary-500">Edit Product</a>'
                    )

                    return redirect('dashboard:product_settings:product_list', prefix=prefix)

            except Exception as e:
                print(e, '=======')
                messages.error(request, f'Error creating product: {str(e)}')
        else:
            errors = {}
            if form.errors:
                errors.update(form.errors)

            print('Please correct the errors below.', errors)
            messages.error(request, 'Please correct the errors below.')
    else:

        form = ProductCreationForm(instance=product,)

    # Get filter data for forms
    categories = Category.objects.filter(is_active=True).order_by('name')
    brands = Brand.objects.filter(is_active=True).order_by('name')
    tags = Tag.objects.filter(is_active=True).order_by('name')
    attributes = Attribute.objects.filter(
        is_variant_option=True).order_by('name')
    # attributes = Attribute.objects.filter(
    #     is_active=True, is_variant_option=True).order_by('name')

    # Serialize data for JavaScript
    categories_json = json.dumps(
        [{'id': str(cat.id), 'name': cat.name, 'parent_id': cat.parent_id} for cat in categories])
    tags_json = json.dumps(
        [{'id': str(tag.id), 'name': tag.name} for tag in tags])
    attributes_json = json.dumps([{
        'id': str(attr.id),
        'name': attr.name,
        'slug': attr.slug,
        'type': attr.attribute_type,
        'values': [{
            'id': str(value.id),
            'value': value.value,
            'slug': value.slug,
            'color_hex': value.color_hex
        } for value in attr.values.all()]
    } for attr in attributes])

    specs_json = json.dumps(product.specifications)
    feature_json = json.dumps(product.features)
    existing_variants_json = json.dumps([
        {
            'id':               str(v.id),
            'sku':              v.sku or '',
            'variant_name':     v.variant_name or '',
            'price':            str(v.price) if v.price else '',
            'compare_at_price': str(v.compare_at_price) if v.compare_at_price else '',
            'stock_quantity':   v.stock_quantity,
            'is_active':        v.is_active,
            'is_default':       v.is_default,
            'option_value_ids': [str(uid) for uid in v.option_values.values_list('id', flat=True)],
        }
        for v in product.variants.prefetch_related('option_values').order_by('pk')
    ])

    context = {
        'form': form,
        'categories': categories,
        'categories_json': categories_json,
        'brands': brands,
        'tags': tags_json,
        'attributes': attributes,
        'is_edit': True,
        'prefix': prefix,
        "product": product,
        "specs_json": specs_json,
        "feature_json": feature_json,
        'attribute_groups': attribute_groups,
        'available_attributes': available_attributes,
        'available_attributes_json': json.dumps(available_attributes_data, cls=DecimalEncoder),
        'existing_variants_json': existing_variants_json,
        'PRODUCT_TYPE_CHOICES': Product.TYPE_CHOICES,
        'sidebar': main_sidebar(prefix),
    }
    # dashboard/products/attributes/form.html

    return render(request, 'dashboard/products/product_form.html', context)


@login_required
@dashboard_prefix_required
def product_delete(request, prefix, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                product_name = product.name
                product.delete()
                FeatureEntitlementEngine().rebuild_quota("max_products")
                messages.success(
                    request, f'Product "{product_name}" deleted successfully.')
        except QuotaExceededError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error deleting product: {str(e)}')

    return redirect('dashboard:product_settings:product_list', prefix=prefix)


@require_http_methods(["GET"])
def generate_slug(request):
    name = request.GET.get('name', '')
    slug = slugify(name)
    return JsonResponse({'slug': slug})
