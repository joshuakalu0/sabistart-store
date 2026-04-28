
"""
ENTERPRISE E-COMMERCE - PRODUCT & ATTRIBUTE VIEWS
Comprehensive, production-ready views for product and attribute management
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count, Prefetch, Avg, Sum
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.forms import formset_factory, inlineformset_factory
import json
from decimal import Decimal

from public.product.models import (
    Product, ProductImage, ProductVideo,
    ProductAttributeValue, ProductVariant, VariantImage,
    Attribute, AttributeValue, AttributeGroup,
    Category, Tag, Brand
)
from .product_form import (
    ProductBasicInfoForm, ProductPricingForm, ProductInventoryForm,
    ProductShippingForm, ProductDigitalForm, ProductSubscriptionForm,
    ProductSEOForm, ProductVisibilityForm, ProductPurchaseSettingsForm,
    ProductImageForm, ProductVideoForm,
    ProductAttributeValueForm, ProductVariantForm,
    ProductCreationForm,
    # AttributeBasicInfoForm, AttributeValuesForm, AttributeSettingsForm,
    # AttributeCreationForm , ProductDocumentForm,, PriceRuleForm
)


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


# ============================================================================
# DECORATORS
# ============================================================================

def staff_required(view_func):
    """Require staff user status"""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied(
                "You must be a staff member to access this page.")
        return view_func(request, *args, **kwargs)
    return wrapper


def product_permission_required(permission):
    """Require specific product permission"""
    from functools import wraps

    @wraps(permission)
    def decorator(view_func):
        @login_required
        @staff_required
        @permission_required(permission, raise_exception=True)
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# PRODUCT VIEWS
# ============================================================================

@login_required
@staff_required
def product_list(request):
    """
    Enterprise-grade product listing with advanced filtering, search, and pagination
    """
    # Get all products with related data optimized
    queryset = Product.objects.select_related(
        'brand',
    ).prefetch_related(
        'categories',
        'tags',
        'variants',
        'images',
        'attribute_values',
    ).all()

    # Search functionality
    search_query = request.GET.get('q', '')
    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(short_description__icontains=search_query) |
            Q(brand__name__icontains=search_query)
        )

    # Filter by product type
    product_type = request.GET.get('product_type', '')
    if product_type:
        queryset = queryset.filter(product_type=product_type)

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    # Filter by category
    category_id = request.GET.get('category', '')
    if category_id:
        queryset = queryset.filter(categories__id=category_id)

    # Filter by brand
    brand_id = request.GET.get('brand', '')
    if brand_id:
        queryset = queryset.filter(brand_id=brand_id)

    # Filter by stock status
    stock_status = request.GET.get('stock_status', '')
    if stock_status:
        queryset = queryset.filter(stock_status=stock_status)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        queryset = queryset.filter(created_at__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__lte=date_to)

    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    valid_sort_fields = ['name', 'sku', 'price',
                         'created_at', 'updated_at', 'sales_count', 'view_count']
    if sort_by.lstrip('-') in valid_sort_fields:
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by('-created_at')

    # Pagination
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    try:
        per_page = int(per_page)
        if per_page > 100:
            per_page = 100
    except (ValueError, TypeError):
        per_page = 20

    paginator = Paginator(queryset, per_page)

    try:
        products = paginator.page(page)
    except PageNotAnInteger:
        products = paginator.page(1)
    except EmptyPage:
        products = paginator.page(paginator.num_pages)

    # Get filter options for template
    categories = Category.objects.filter(is_active=True).order_by('name')
    brands = Brand.objects.filter(is_active=True).order_by('name')

    # Statistics for dashboard
    stats = {
        'total': Product.objects.count(),
        'published': Product.objects.filter(status='published').count(),
        'draft': Product.objects.filter(status='draft').count(),
        'low_stock': Product.objects.filter(
            stock_quantity__lte=low_stock_threshold,
            manage_stock=True
        ).count() if (low_stock_threshold := 5) else 0,
        'out_of_stock': Product.objects.filter(stock_status='out_of_stock').count(),
    }

    context = {
        'products': products,
        'search_query': search_query,
        'product_type': product_type,
        'status': status,
        'category_id': category_id,
        'brand_id': brand_id,
        'stock_status': stock_status,
        'date_from': date_from,
        'date_to': date_to,
        'sort_by': sort_by,
        'categories': categories,
        'brands': brands,
        'stats': stats,
        'page': page,
        'per_page': per_page,
        'paginator': paginator,
        'PRODUCT_TYPE_CHOICES': Product.TYPE_CHOICES,
        'STATUS_CHOICES': Product._meta.get_field('status').choices,
        'STOCK_STATUS_CHOICES': Product._meta.get_field('stock_status').choices,
    }

    return render(request, 'products/product_list.html', context)


# @login_required
# @staff_required
# @permission_required('products.add_product', raise_exception=True)
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

    if request.method == 'POST':
        form = ProductCreationForm(
            data=request.POST, files=request.FILES, prefix='product')

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save product
                    product = form.save(commit=True)

                    # Log creation
                    messages.success(
                        request,
                        f'Product "{product.name}" created successfully! '
                        f'<a href="{reverse("product_edit", kwargs={"pk": product.pk})}" '
                        f'class="font-medium text-primary-600 hover:text-primary-500">Edit Product</a>'
                    )

                    return redirect('product_list')

            except Exception as e:
                messages.error(request, f'Error creating product: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductCreationForm(prefix='product')

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
        [{'id': cat.id, 'name': cat.name, 'parent_id': cat.parent_id} for cat in categories])
    tags_json = json.dumps([{'id': tag.id, 'name': tag.name} for tag in tags])
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
    }
    # dashboard/products/attributes/form.html

    return render(request, 'dashboard/products/product_form.html', context)


@login_required
@staff_required
@permission_required('products.change_product', raise_exception=True)
def product_edit(request, pk):
    """
    Edit existing product with all related forms and formsets
    Shares template with product_create
    """
    product = get_object_or_404(
        Product.objects.select_related('brand').prefetch_related(
            'categories', 'tags', 'images', 'videos', 'documents',
            'attribute_values', 'variants', 'price_rules'
        ),
        pk=pk
    )

    if request.method == 'POST':
        form = ProductCreationForm(
            data=request.POST,
            files=request.FILES,
            instance=product,
            prefix='product'
        )

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save product
                    product = form.save(commit=True)

                    # Update timestamp
                    product.updated_at = timezone.now()
                    product.save(update_fields=['updated_at'])

                    messages.success(
                        request,
                        f'Product "{product.name}" updated successfully!'
                    )

                    return redirect('product_list')

            except Exception as e:
                messages.error(request, f'Error updating product: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductCreationForm(instance=product, prefix='product')

    # Get filter data for forms
    categories = Category.objects.filter(is_active=True).order_by('name')
    brands = Brand.objects.filter(is_active=True).order_by('name')
    tags = Tag.objects.filter(is_active=True).order_by('name')
    attributes = Attribute.objects.filter(
        is_active=True, is_variant_option=True).order_by('name')

    # Serialize data for JavaScript
    categories_json = json.dumps(
        [{'id': cat.id, 'name': cat.name, 'parent_id': cat.parent_id} for cat in categories])
    tags_json = json.dumps([{'id': tag.id, 'name': tag.name} for tag in tags])
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
        'product': product,
        'categories': categories,
        'categories_json': categories_json,
        'brands': brands,
        'tags': tags_json,
        'attributes': attributes_json,
        'is_edit': True,
        'PRODUCT_TYPE_CHOICES': Product.TYPE_CHOICES,
    }

    return render(request, 'products/product_form.html', context)


@login_required
@staff_required
@permission_required('products.delete_product', raise_exception=True)
@require_http_methods(["POST"])
def product_delete(request, pk):
    """
    Delete product (soft delete by setting status to archived)
    """
    product = get_object_or_404(Product, pk=pk)

    # Soft delete - archive the product
    product.status = 'archived'
    product.is_active = False
    product.save(update_fields=['status', 'is_active', 'updated_at'])

    messages.success(request, f'Product "{product.name}" has been archived.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Product archived successfully'})

    return redirect('product_list')


@login_required
@staff_required
@require_http_methods(["POST"])
def product_duplicate(request, pk):
    """
    Duplicate an existing product with all its data
    """
    original = get_object_or_404(
        Product.objects.prefetch_related(
            'categories', 'tags', 'images', 'attribute_values'
        ),
        pk=pk
    )

    try:
        with transaction.atomic():
            # Create new product instance
            original.pk = None
            original.id = None
            original.name = f"{original.name} (Copy)"
            original.sku = f"{original.sku}-COPY"
            original.slug = f"{original.slug}-copy"
            original.status = 'draft'
            original.sales_count = 0
            original.view_count = 0
            original.published_at = None

            original.save()

            # Copy categories and tags
            original.categories.set(original.categories.all())
            original.tags.set(original.tags.all())

            # Copy images
            for image in ProductImage.objects.filter(product=pk):
                image.pk = None
                image.id = None
                image.product = original
                image.save()

            messages.success(
                request,
                f'Product duplicated successfully! '
                f'<a href="{reverse("product_edit", kwargs={"pk": original.pk})}" '
                f'class="font-medium text-primary-600 hover:text-primary-500">Edit New Product</a>'
            )

            return redirect('product_edit', pk=original.pk)

    except Exception as e:
        messages.error(request, f'Error duplicating product: {str(e)}')
        return redirect('product_list')


@login_required
@staff_required
@require_http_methods(["POST"])
def product_toggle_status(request, pk):
    """
    Toggle product status (publish/unpublish)
    """
    product = get_object_or_404(Product, pk=pk)

    if product.status == 'published':
        product.status = 'draft'
        product.published_at = None
        message = f'Product "{product.name}" unpublished.'
    else:
        product.status = 'published'
        product.published_at = timezone.now()
        message = f'Product "{product.name}" published.'

    product.save(update_fields=['status', 'published_at', 'updated_at'])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': message,
            'status': product.status,
            'published_at': product.published_at.isoformat() if product.published_at else None
        })

    messages.success(request, message)
    return redirect('product_list')


# ============================================================================
# ATTRIBUTE VIEWS
# ============================================================================

@login_required
@staff_required
def attribute_list(request):
    """
    Enterprise-grade attribute listing with advanced filtering and search
    """
    # Get all attributes with related data optimized
    queryset = Attribute.objects.select_related(
        'group'
    ).prefetch_related(
        'values',
        'product_values'
    ).annotate(
        value_count=Count('values', distinct=True),
        product_count=Count('product_values', distinct=True)
    ).all()

    # Search functionality
    search_query = request.GET.get('q', '')
    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(slug__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Filter by attribute type
    attribute_type = request.GET.get('attribute_type', '')
    if attribute_type:
        queryset = queryset.filter(attribute_type=attribute_type)

    # Filter by group
    group_id = request.GET.get('group', '')
    if group_id:
        queryset = queryset.filter(group_id=group_id)

    # Filter by variant option
    is_variant = request.GET.get('is_variant', '')
    if is_variant == 'true':
        queryset = queryset.filter(is_variant_option=True)
    elif is_variant == 'false':
        queryset = queryset.filter(is_variant_option=False)

    # Filter by status
    is_active = request.GET.get('is_active', '')
    if is_active == 'true':
        queryset = queryset.filter(is_active=True)
    elif is_active == 'false':
        queryset = queryset.filter(is_active=False)

    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    valid_sort_fields = ['name', 'slug',
                         'attribute_type', 'display_order', 'created_at']
    if sort_by.lstrip('-') in valid_sort_fields:
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by('-created_at')

    # Pagination
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    try:
        per_page = int(per_page)
        if per_page > 100:
            per_page = 100
    except (ValueError, TypeError):
        per_page = 20

    paginator = Paginator(queryset, per_page)

    try:
        attributes = paginator.page(page)
    except PageNotAnInteger:
        attributes = paginator.page(1)
    except EmptyPage:
        attributes = paginator.page(paginator.num_pages)

    # Get filter options for template
    groups = AttributeGroup.objects.all().order_by('name')

    # Statistics for dashboard
    stats = {
        'total': Attribute.objects.count(),
        'active': Attribute.objects.filter(is_active=True).count(),
        'inactive': Attribute.objects.filter(is_active=False).count(),
        'variant_options': Attribute.objects.filter(is_variant_option=True).count(),
    }

    context = {
        'attributes': attributes,
        'search_query': search_query,
        'attribute_type': attribute_type,
        'group_id': group_id,
        'is_variant': is_variant,
        'is_active': is_active,
        'sort_by': sort_by,
        'groups': groups,
        'stats': stats,
        'page': page,
        'per_page': per_page,
        'paginator': paginator,
        'ATTRIBUTE_TYPE_CHOICES': Attribute.TYPE_CHOICES,
    }

    return render(request, 'attributes/attribute_list.html', context)


@login_required
@staff_required
@permission_required('attributes.add_attribute', raise_exception=True)
def attribute_create(request):
    """
    Create new attribute with all related forms
    Shares template with attribute_edit
    """
    if request.method == 'POST':
        form = AttributeCreationForm(data=request.POST, prefix='attribute')

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save attribute
                    attribute = form.save(commit=True)

                    # Save attribute values if provided
                    values_data = request.POST.getlist('attribute_values[]')
                    value_colors = request.POST.getlist(
                        'attribute_value_colors[]')
                    value_prices = request.POST.getlist(
                        'attribute_value_prices[]')

                    for i, value in enumerate(values_data):
                        if value.strip():
                            AttributeValue.objects.create(
                                attribute=attribute,
                                value=value.strip(),
                                color_hex=value_colors[i] if i < len(
                                    value_colors) else '',
                                extra_price=value_prices[i] if i < len(
                                    value_prices) else 0,
                                display_order=i
                            )

                    messages.success(
                        request,
                        f'Attribute "{attribute.name}" created successfully! '
                        f'<a href="{reverse("attribute_edit", kwargs={"pk": attribute.pk})}" '
                        f'class="font-medium text-primary-600 hover:text-primary-500">Edit Attribute</a>'
                    )

                    return redirect('attribute_list')

            except Exception as e:
                messages.error(request, f'Error creating attribute: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AttributeCreationForm(prefix='attribute')

    # Get filter data for forms
    groups = AttributeGroup.objects.all().order_by('name')

    context = {
        'form': form,
        'groups': groups,
        'is_edit': False,
        'ATTRIBUTE_TYPE_CHOICES': Attribute.TYPE_CHOICES,
    }

    return render(request, 'attributes/attribute_form.html', context)


@login_required
@staff_required
@permission_required('attributes.change_attribute', raise_exception=True)
def attribute_edit(request, pk):
    """
    Edit existing attribute with all related forms
    Shares template with attribute_create
    """
    attribute = get_object_or_404(
        Attribute.objects.select_related('group').prefetch_related('values'),
        pk=pk
    )

    if request.method == 'POST':
        form = AttributeCreationForm(
            data=request.POST,
            instance=attribute,
            prefix='attribute'
        )

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save attribute
                    attribute = form.save(commit=True)

                    # Update existing values or create new ones
                    value_ids = request.POST.getlist('value_ids[]')
                    values_data = request.POST.getlist('attribute_values[]')
                    value_colors = request.POST.getlist(
                        'attribute_value_colors[]')
                    value_prices = request.POST.getlist(
                        'attribute_value_prices[]')
                    value_active = request.POST.getlist('value_active[]')

                    # Delete values that were removed
                    current_ids = [int(id) for id in value_ids if id]
                    AttributeValue.objects.filter(
                        attribute=attribute
                    ).exclude(id__in=current_ids).delete()

                    # Update or create values
                    for i, value_id in enumerate(value_ids):
                        value_data = {
                            'value': values_data[i].strip() if i < len(values_data) else '',
                            'color_hex': value_colors[i] if i < len(value_colors) else '',
                            'extra_price': value_prices[i] if i < len(value_prices) else 0,
                            'is_active': i < len(value_active) and value_active[i] == 'on',
                            'display_order': i,
                        }

                        if value_id:
                            # Update existing
                            try:
                                attr_value = AttributeValue.objects.get(
                                    id=value_id,
                                    attribute=attribute
                                )
                                for key, val in value_data.items():
                                    setattr(attr_value, key, val)
                                attr_value.save()
                            except AttributeValue.DoesNotExist:
                                pass
                        elif value_data['value']:
                            # Create new
                            AttributeValue.objects.create(
                                attribute=attribute,
                                **value_data
                            )

                    attribute.updated_at = timezone.now()
                    attribute.save(update_fields=['updated_at'])

                    messages.success(
                        request,
                        f'Attribute "{attribute.name}" updated successfully!'
                    )

                    return redirect('attribute_list')

            except Exception as e:
                messages.error(request, f'Error updating attribute: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AttributeCreationForm(instance=attribute, prefix='attribute')

    # Get filter data for forms
    groups = AttributeGroup.objects.all().order_by('name')

    context = {
        'form': form,
        'attribute': attribute,
        'groups': groups,
        'is_edit': True,
        'ATTRIBUTE_TYPE_CHOICES': Attribute.TYPE_CHOICES,
    }

    return render(request, 'attributes/attribute_form.html', context)


@login_required
@staff_required
@permission_required('attributes.delete_attribute', raise_exception=True)
@require_http_methods(["POST"])
def attribute_delete(request, pk):
    """
    Delete attribute (soft delete by setting is_active to False)
    """
    attribute = get_object_or_404(Attribute, pk=pk)

    # Check if attribute is used in any products
    product_count = attribute.product_values.count()
    if product_count > 0:
        messages.error(
            request,
            f'Cannot delete attribute. It is used in {product_count} product(s).'
        )
        return redirect('attribute_list')

    # Soft delete
    attribute.is_active = False
    attribute.save(update_fields=['is_active', 'updated_at'])

    messages.success(
        request, f'Attribute "{attribute.name}" has been deactivated.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Attribute deactivated successfully'})

    return redirect('attribute_list')


@login_required
@staff_required
@require_http_methods(["POST"])
def attribute_toggle_status(request, pk):
    """
    Toggle attribute status (active/inactive)
    """
    attribute = get_object_or_404(Attribute, pk=pk)

    attribute.is_active = not attribute.is_active
    attribute.save(update_fields=['is_active', 'updated_at'])

    status = 'activated' if attribute.is_active else 'deactivated'
    message = f'Attribute "{attribute.name}" {status}.'

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': message,
            'is_active': attribute.is_active
        })

    messages.success(request, message)
    return redirect('attribute_list')


# ============================================================================
# AJAX ENDPOINTS FOR DYNAMIC FUNCTIONALITY
# ============================================================================

@login_required
@staff_required
@require_http_methods(["GET"])
def ajax_search_categories(request):
    """
    AJAX endpoint for searching categories (for multi-select)
    """
    query = request.GET.get('q', '')
    limit = request.GET.get('limit', 20)

    try:
        limit = int(limit)
        if limit > 100:
            limit = 100
    except (ValueError, TypeError):
        limit = 20

    categories = Category.objects.filter(is_active=True)

    if query:
        categories = categories.filter(
            Q(name__icontains=query) |
            Q(slug__icontains=query)
        )

    categories = categories.order_by('name')[:limit]

    data = {
        'results': [
            {
                'id': str(cat.id),
                'name': cat.name,
                'slug': cat.slug,
                'parent': cat.parent.name if cat.parent else None,
            }
            for cat in categories
        ]
    }

    return JsonResponse(data)


@login_required
@staff_required
@require_http_methods(["GET"])
def ajax_search_tags(request):
    """
    AJAX endpoint for searching tags (for multi-select)
    """
    query = request.GET.get('q', '')
    limit = request.GET.get('limit', 20)

    try:
        limit = int(limit)
        if limit > 100:
            limit = 100
    except (ValueError, TypeError):
        limit = 20

    tags = Tag.objects.filter(is_active=True)

    if query:
        tags = tags.filter(
            Q(name__icontains=query) |
            Q(slug__icontains=query)
        )

    tags = tags.order_by('name')[:limit]

    data = {
        'results': [
            {
                'id': str(tag.id),
                'name': tag.name,
                'slug': tag.slug,
                'color': tag.color,
            }
            for tag in tags
        ]
    }

    return JsonResponse(data)


@login_required
@staff_required
@require_http_methods(["POST"])
def ajax_create_tag(request):
    """
    AJAX endpoint for creating new tag on the fly
    """
    name = request.POST.get('name', '').strip()

    if not name:
        return JsonResponse({
            'success': False,
            'error': 'Tag name is required'
        }, status=400)

    # Check if tag already exists
    tag, created = Tag.objects.get_or_create(
        slug=slugify(name),
        defaults={'name': name}
    )

    if not created:
        return JsonResponse({
            'success': False,
            'error': 'Tag already exists'
        }, status=400)

    return JsonResponse({
        'success': True,
        'tag': {
            'id': str(tag.id),
            'name': tag.name,
            'slug': tag.slug,
            'color': tag.color,
        }
    })


@login_required
@staff_required
@require_http_methods(["GET"])
def ajax_get_attribute_values(request):
    """
    AJAX endpoint for getting attribute values based on attribute ID
    """
    attribute_id = request.GET.get('attribute_id', '')

    if not attribute_id:
        return JsonResponse({'results': []})

    try:
        attribute = Attribute.objects.get(id=attribute_id)
        values = attribute.values.filter(
            is_active=True).order_by('display_order', 'value')

        data = {
            'results': [
                {
                    'id': str(val.id),
                    'value': val.value,
                    'slug': val.slug,
                    'color_hex': val.color_hex,
                    'extra_price': str(val.extra_price),
                }
                for val in values
            ]
        }

        return JsonResponse(data)

    except Attribute.DoesNotExist:
        return JsonResponse({'results': []})


@login_required
@staff_required
@require_http_methods(["POST"])
def ajax_generate_variants(request, product_id):
    """
    AJAX endpoint for generating product variants from selected attributes
    """
    product = get_object_or_404(Product, id=product_id)

    if product.product_type != 'variable':
        return JsonResponse({
            'success': False,
            'error': 'Product must be of type "variable" to generate variants'
        }, status=400)

    try:
        data = json.loads(request.body)
        selected_attributes = data.get('attributes', [])

        if not selected_attributes:
            return JsonResponse({
                'success': False,
                'error': 'No attributes selected'
            }, status=400)

        # Get attribute values for each selected attribute
        attribute_data = []
        for attr_data in selected_attributes:
            attribute_id = attr_data.get('attribute_id')
            value_ids = attr_data.get('value_ids', [])

            if attribute_id and value_ids:
                attribute = Attribute.objects.get(id=attribute_id)
                values = AttributeValue.objects.filter(
                    id__in=value_ids,
                    attribute=attribute
                )
                attribute_data.append({
                    'attribute': attribute,
                    'values': list(values)
                })

        if not attribute_data:
            return JsonResponse({
                'success': False,
                'error': 'No valid attribute values found'
            }, status=400)

        # Generate all combinations
        from itertools import product
        combinations = list(product(*[attr['values']
                            for attr in attribute_data]))

        # Create variants
        variants_created = []
        for combo in combinations:
            # Generate SKU
            sku_parts = [product.sku]
            for value in combo:
                sku_parts.append(value.slug.upper()[:3])
            sku = '-'.join(sku_parts)[:100]

            # Check if variant already exists
            variant, created = ProductVariant.objects.get_or_create(
                product=product,
                sku=sku,
                defaults={
                    'price': product.price or Decimal('0.00'),
                    'stock_quantity': 0,
                }
            )

            # Set option values
            variant.option_values.set(combo)

            # Generate variant name
            variant_name = ' / '.join([value.value for value in combo])
            variant.variant_name = variant_name
            variant.save()

            variants_created.append({
                'id': str(variant.id),
                'sku': variant.sku,
                'name': variant_name,
                'price': str(variant.price),
                'created': created,
            })

        return JsonResponse({
            'success': True,
            'message': f'{len(variants_created)} variant(s) generated',
            'variants': variants_created,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@staff_required
@require_http_methods(["POST"])
def ajax_upload_image(request):
    """
    AJAX endpoint for uploading product images
    """
    if 'image' not in request.FILES:
        return JsonResponse({
            'success': False,
            'error': 'No image file provided'
        }, status=400)

    image_file = request.FILES['image']
    product_id = request.POST.get('product_id')

    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if image_file.content_type not in allowed_types:
        return JsonResponse({
            'success': False,
            'error': 'Invalid file type. Allowed: JPEG, PNG, GIF, WebP'
        }, status=400)

    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    if image_file.size > max_size:
        return JsonResponse({
            'success': False,
            'error': 'File too large. Maximum size: 10MB'
        }, status=400)

    try:
        if product_id:
            product = Product.objects.get(id=product_id)
        else:
            product = None

        # Create image instance
        product_image = ProductImage.objects.create(
            product=product,
            image=image_file,
            alt_text=request.POST.get('alt_text', ''),
            title=request.POST.get('title', ''),
            caption=request.POST.get('caption', ''),
            is_primary=request.POST.get('is_primary') == 'true',
            display_order=request.POST.get('display_order', 0),
        )

        return JsonResponse({
            'success': True,
            'image': {
                'id': str(product_image.id),
                'url': product_image.image.url,
                'thumbnail_url': product_image.thumbnail.url if product_image.thumbnail else None,
                'alt_text': product_image.alt_text,
                'title': product_image.title,
                'is_primary': product_image.is_primary,
                'display_order': product_image.display_order,
            }
        })

    except Product.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Product not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@staff_required
@require_http_methods(["POST"])
def ajax_delete_image(request, image_id):
    """
    AJAX endpoint for deleting product images
    """
    try:
        image = ProductImage.objects.get(id=image_id)
        image.delete()

        return JsonResponse({
            'success': True,
            'message': 'Image deleted successfully'
        })

    except ProductImage.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Image not found'
        }, status=404)


@login_required
@staff_required
@require_http_methods(["POST"])
def ajax_set_primary_image(request):
    """
    AJAX endpoint for setting primary product image
    """
    image_id = request.POST.get('image_id')
    product_id = request.POST.get('product_id')

    try:
        image = ProductImage.objects.get(id=image_id, product_id=product_id)

        # Set all other images to not primary
        ProductImage.objects.filter(
            product_id=product_id).update(is_primary=False)

        # Set this image as primary
        image.is_primary = True
        image.save(update_fields=['is_primary'])

        return JsonResponse({
            'success': True,
            'message': 'Primary image updated successfully'
        })

    except ProductImage.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Image not found'
        }, status=404)


# ============================================================================
# URL PATTERNS
# ============================================================================

"""
Add these to your urls.py:

from django.urls import path
from . import views

urlpatterns = [
    # Product URLs
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<uuid:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<uuid:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/<uuid:pk>/duplicate/', views.product_duplicate, name='product_duplicate'),
    path('products/<uuid:pk>/toggle-status/', views.product_toggle_status, name='product_toggle_status'),

    # Attribute URLs
    path('attributes/', views.attribute_list, name='attribute_list'),
    path('attributes/create/', views.attribute_create, name='attribute_create'),
    path('attributes/<uuid:pk>/edit/', views.attribute_edit, name='attribute_edit'),
    path('attributes/<uuid:pk>/delete/', views.attribute_delete, name='attribute_delete'),
    path('attributes/<uuid:pk>/toggle-status/', views.attribute_toggle_status, name='attribute_toggle_status'),

    # AJAX Endpoints
    path('ajax/search/categories/', views.ajax_search_categories, name='ajax_search_categories'),
    path('ajax/search/tags/', views.ajax_search_tags, name='ajax_search_tags'),
    path('ajax/create/tag/', views.ajax_create_tag, name='ajax_create_tag'),
    path('ajax/attribute-values/', views.ajax_get_attribute_values, name='ajax_get_attribute_values'),
    path('ajax/products/<uuid:product_id>/generate-variants/', views.ajax_generate_variants, name='ajax_generate_variants'),
    path('ajax/upload/image/', views.ajax_upload_image, name='ajax_upload_image'),
    path('ajax/images/<uuid:image_id>/delete/', views.ajax_delete_image, name='ajax_delete_image'),
    path('ajax/images/set-primary/', views.ajax_set_primary_image, name='ajax_set_primary_image'),
]
"""


# ============================================================================
# MIXINS FOR CLASS-BASED VIEWS (Alternative Approach)
# ============================================================================

class ProductPermissionMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Mixin for product-related permissions"""
    login_url = '/admin/login/'
    raise_exception = True


class AttributePermissionMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Mixin for attribute-related permissions"""
    login_url = '/admin/login/'
    raise_exception = True


class ProductListView(ProductPermissionMixin, ListView):
    """Class-based view for product listing"""
    model = Product
    template_name = 'products/product_list.html'
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        queryset = Product.objects.select_related('brand').prefetch_related(
            'categories', 'tags', 'images'
        ).all()

        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search)
            )

        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Filter by type
        product_type = self.request.GET.get('product_type')
        if product_type:
            queryset = queryset.filter(product_type=product_type)

        # Sorting
        sort = self.request.GET.get('sort', '-created_at')
        queryset = queryset.order_by(sort)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stats'] = {
            'total': Product.objects.count(),
            'published': Product.objects.filter(status='published').count(),
            'draft': Product.objects.filter(status='draft').count(),
        }
        return context


class ProductCreateView(ProductPermissionMixin, CreateView):
    """Class-based view for product creation"""
    model = Product
    template_name = 'products/product_form.html'
    fields = '__all__'

    def get_success_url(self):
        messages.success(self.request, 'Product created successfully!')
        return reverse('product_list')


class ProductUpdateView(ProductPermissionMixin, UpdateView):
    """Class-based view for product update"""
    model = Product
    template_name = 'products/product_form.html'
    fields = '__all__'

    def get_success_url(self):
        messages.success(self.request, 'Product updated successfully!')
        return reverse('product_list')


class AttributeListView(AttributePermissionMixin, ListView):
    """Class-based view for attribute listing"""
    model = Attribute
    template_name = 'attributes/attribute_list.html'
    context_object_name = 'attributes'
    paginate_by = 20

    def get_queryset(self):
        queryset = Attribute.objects.select_related('group').prefetch_related(
            'values'
        ).annotate(
            value_count=Count('values', distinct=True),
            product_count=Count('product_values', distinct=True)
        ).all()

        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(slug__icontains=search)
            )

        # Filter by type
        attr_type = self.request.GET.get('attribute_type')
        if attr_type:
            queryset = queryset.filter(attribute_type=attr_type)

        # Filter by active status
        is_active = self.request.GET.get('is_active')
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)
        elif is_active == 'false':
            queryset = queryset.filter(is_active=False)

        return queryset


class AttributeCreateView(AttributePermissionMixin, CreateView):
    """Class-based view for attribute creation"""
    model = Attribute
    template_name = 'attributes/attribute_form.html'
    fields = '__all__'

    def get_success_url(self):
        messages.success(self.request, 'Attribute created successfully!')
        return reverse('attribute_list')


class AttributeUpdateView(AttributePermissionMixin, UpdateView):
    """Class-based view for attribute update"""
    model = Attribute
    template_name = 'attributes/attribute_form.html'
    fields = '__all__'

    def get_success_url(self):
        messages.success(self.request, 'Attribute updated successfully!')
        return reverse('attribute_list')
