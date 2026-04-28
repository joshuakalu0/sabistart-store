"""
COMPREHENSIVE E-COMMERCE VIEWS
===============================
Complete views for managing all aspects of the e-commerce system.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, F
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from decimal import Decimal
import json

from .models import (
    Category, Tag, Brand, Attribute, AttributeGroup, AttributeValue,
    Product, ProductImage, ProductVideo, ProductDocument, ProductAttributeValue,
    ProductVariant, VariantImage, PriceRule, Promotion, Coupon, CouponUsage,
    ProductBundle, BundleItem, GroupedProduct, Review, ReviewImage, QA, QAAnswer,
    Warehouse, InventoryLocation, StockMovement, DigitalProduct, GiftCard,
    SubscriptionPlan, LoyaltyProgram, LoyaltyAccount, Wishlist, WishlistItem,
    ProductView as ProductViewLog, ProductSearch, ProductComparison
)


# ============================================================================
# DASHBOARD
# ============================================================================

@login_required
@permission_required('catalog.view_product', raise_exception=True)
def dashboard(request):
    """Main dashboard with overview statistics"""

    # Get stats
    total_products = Product.objects.filter(is_active=True).count()
    total_categories = Category.objects.filter(is_active=True).count()
    total_brands = Brand.objects.filter(is_active=True).count()
    low_stock_count = ProductVariant.objects.filter(
        stock_quantity__lte=F('low_stock_threshold'),
        is_active=True
    ).count()

    # Recent products
    recent_products = Product.objects.filter(
        is_active=True
    ).select_related('brand').prefetch_related('images').order_by('-created_at')[:5]

    # Pending reviews
    pending_reviews = Review.objects.filter(status='pending').count()

    # Active promotions
    active_promotions = Promotion.objects.filter(
        is_active=True,
        starts_at__lte=timezone.now(),
        ends_at__gte=timezone.now()
    ).count()

    context = {
        'total_products': total_products,
        'total_categories': total_categories,
        'total_brands': total_brands,
        'low_stock_count': low_stock_count,
        'recent_products': recent_products,
        'pending_reviews': pending_reviews,
        'active_promotions': active_promotions,
    }

    return render(request, 'ecommerce/dashboard.html', context)


# ============================================================================
# CATEGORIES
# ============================================================================

@login_required
@permission_required('catalog.view_category', raise_exception=True)
def category_list(request):
    """List all categories with hierarchy"""

    # Get root categories (no parent)
    root_categories = Category.objects.filter(
        parent=None
    ).prefetch_related('children').order_by('display_order', 'name')

    context = {
        'categories': root_categories,
    }

    return render(request, 'ecommerce/categories/list.html', context)


@login_required
@permission_required('catalog.add_category', raise_exception=True)
def category_create(request):
    """Create new category"""

    if request.method == 'POST':
        # Handle form submission
        name = request.POST.get('name')
        parent_id = request.POST.get('parent')
        description = request.POST.get('description', '')
        is_active = request.POST.get('is_active') == 'on'

        category = Category.objects.create(
            name=name,
            description=description,
            is_active=is_active
        )

        if parent_id:
            category.parent_id = parent_id
            category.save()

        # Handle image upload
        if 'image' in request.FILES:
            category.image = request.FILES['image']
            category.save()

        messages.success(request, f'Category "{name}" created successfully!')
        return redirect('category_list')

    # GET request - show form
    all_categories = Category.objects.filter(is_active=True).order_by('name')

    context = {
        'all_categories': all_categories,
    }

    return render(request, 'ecommerce/categories/create.html', context)


@login_required
@permission_required('catalog.change_category', raise_exception=True)
def category_edit(request, category_id):
    """Edit existing category"""

    category = get_object_or_404(Category, id=category_id)

    if request.method == 'POST':
        category.name = request.POST.get('name')
        category.description = request.POST.get('description', '')
        category.is_active = request.POST.get('is_active') == 'on'

        parent_id = request.POST.get('parent')
        if parent_id:
            category.parent_id = parent_id
        else:
            category.parent = None

        if 'image' in request.FILES:
            category.image = request.FILES['image']

        category.save()

        messages.success(request, f'Category "{category.name}" updated successfully!')
        return redirect('category_list')

    all_categories = Category.objects.filter(is_active=True).exclude(id=category_id).order_by('name')

    context = {
        'category': category,
        'all_categories': all_categories,
    }

    return render(request, 'ecommerce/categories/edit.html', context)


# ============================================================================
# BRANDS
# ============================================================================

@login_required
@permission_required('catalog.view_brand', raise_exception=True)
def brand_list(request):
    """List all brands"""

    brands = Brand.objects.all().order_by('name')

    # Pagination
    paginator = Paginator(brands, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
    }

    return render(request, 'ecommerce/brands/list.html', context)


@login_required
@permission_required('catalog.add_brand', raise_exception=True)
def brand_create(request):
    """Create new brand"""

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        website = request.POST.get('website', '')
        is_active = request.POST.get('is_active') == 'on'

        brand = Brand.objects.create(
            name=name,
            description=description,
            website=website,
            is_active=is_active
        )

        if 'logo' in request.FILES:
            brand.logo = request.FILES['logo']
            brand.save()

        messages.success(request, f'Brand "{name}" created successfully!')
        return redirect('brand_list')

    return render(request, 'ecommerce/brands/create.html')


@login_required
@permission_required('catalog.change_brand', raise_exception=True)
def brand_edit(request, brand_id):
    """Edit existing brand"""

    brand = get_object_or_404(Brand, id=brand_id)

    if request.method == 'POST':
        brand.name = request.POST.get('name')
        brand.description = request.POST.get('description', '')
        brand.website = request.POST.get('website', '')
        brand.is_active = request.POST.get('is_active') == 'on'

        if 'logo' in request.FILES:
            brand.logo = request.FILES['logo']

        brand.save()

        messages.success(request, f'Brand "{brand.name}" updated successfully!')
        return redirect('brand_list')

    context = {
        'brand': brand,
    }

    return render(request, 'ecommerce/brands/edit.html', context)


# ============================================================================
# ATTRIBUTES
# ============================================================================

@login_required
@permission_required('catalog.view_attribute', raise_exception=True)
def attribute_list(request):
    """List all attributes"""

    attributes = Attribute.objects.select_related('group').prefetch_related('values').order_by('display_order', 'name')

    context = {
        'attributes': attributes,
    }

    return render(request, 'ecommerce/attributes/list.html', context)


@login_required
@permission_required('catalog.add_attribute', raise_exception=True)
def attribute_create(request):
    """Create new attribute"""

    if request.method == 'POST':
        name = request.POST.get('name')
        attribute_type = request.POST.get('attribute_type')
        is_variant_option = request.POST.get('is_variant_option') == 'on'
        is_filterable = request.POST.get('is_filterable') == 'on'

        attribute = Attribute.objects.create(
            name=name,
            attribute_type=attribute_type,
            is_variant_option=is_variant_option,
            is_filterable=is_filterable
        )

        messages.success(request, f'Attribute "{name}" created successfully!')
        return redirect('attribute_edit', attribute_id=attribute.id)

    context = {
        'attribute_types': Attribute.TYPE_CHOICES,
    }

    return render(request, 'ecommerce/attributes/create.html', context)


@login_required
@permission_required('catalog.change_attribute', raise_exception=True)
def attribute_edit(request, attribute_id):
    """Edit attribute and manage its values"""

    attribute = get_object_or_404(Attribute, id=attribute_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_attribute':
            attribute.name = request.POST.get('name')
            attribute.attribute_type = request.POST.get('attribute_type')
            attribute.is_variant_option = request.POST.get('is_variant_option') == 'on'
            attribute.is_filterable = request.POST.get('is_filterable') == 'on'
            attribute.save()
            messages.success(request, f'Attribute "{attribute.name}" updated!')

        elif action == 'add_value':
            value = request.POST.get('value')
            color_hex = request.POST.get('color_hex', '')

            AttributeValue.objects.create(
                attribute=attribute,
                value=value,
                color_hex=color_hex
            )
            messages.success(request, f'Value "{value}" added!')

        return redirect('attribute_edit', attribute_id=attribute_id)

    context = {
        'attribute': attribute,
        'values': attribute.values.all().order_by('display_order', 'value'),
        'attribute_types': Attribute.TYPE_CHOICES,
    }

    return render(request, 'ecommerce/attributes/edit.html', context)


# ============================================================================
# PRODUCTS - MAIN VIEWS
# ============================================================================

@login_required
@permission_required('catalog.view_product', raise_exception=True)
def product_list(request):
    """List all products with filters"""

    products = Product.objects.select_related('brand').prefetch_related('images', 'categories').order_by('-created_at')

    # Filters
    search = request.GET.get('search')
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(sku__icontains=search) |
            Q(description__icontains=search)
        )

    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(categories__id=category_id)

    brand_id = request.GET.get('brand')
    if brand_id:
        products = products.filter(brand_id=brand_id)

    status = request.GET.get('status')
    if status:
        products = products.filter(status=status)

    # Pagination
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Data for filters
    categories = Category.objects.filter(is_active=True).order_by('name')
    brands = Brand.objects.filter(is_active=True).order_by('name')

    context = {
        'page_obj': page_obj,
        'categories': categories,
        'brands': brands,
        'current_filters': {
            'search': search or '',
            'category': category_id or '',
            'brand': brand_id or '',
            'status': status or '',
        }
    }

    return render(request, 'ecommerce/products/list.html', context)


@login_required
@permission_required('catalog.add_product', raise_exception=True)
def product_create(request):
    """Create new product - Step 1: Basic Info"""

    if request.method == 'POST':
        # Basic product info
        name = request.POST.get('name')
        sku = request.POST.get('sku')
        product_type = request.POST.get('product_type', 'simple')
        brand_id = request.POST.get('brand')

        # Create product
        product = Product.objects.create(
            name=name,
            sku=sku,
            product_type=product_type,
            brand_id=brand_id if brand_id else None,
            description=request.POST.get('description', ''),
            short_description=request.POST.get('short_description', ''),
            status='draft'
        )

        # Add categories
        category_ids = request.POST.getlist('categories')
        if category_ids:
            product.categories.set(category_ids)

        # For simple products, create a default variant
        if product_type == 'simple':
            price = request.POST.get('price')
            stock = request.POST.get('stock_quantity', 0)

            ProductVariant.objects.create(
                product=product,
                sku=sku,
                price=price,
                stock_quantity=stock,
                is_default=True
            )

        messages.success(request, f'Product "{name}" created! Now add images and details.')
        return redirect('product_edit', product_id=product.id)

    # GET - show form
    categories = Category.objects.filter(is_active=True).order_by('name')
    brands = Brand.objects.filter(is_active=True).order_by('name')

    context = {
        'categories': categories,
        'brands': brands,
        'product_types': Product.TYPE_CHOICES,
    }

    return render(request, 'ecommerce/products/create.html', context)


@login_required
@permission_required('catalog.change_product', raise_exception=True)
def product_edit(request, product_id):
    """Edit product - Complete management page"""

    product = get_object_or_404(
        Product.objects.select_related('brand').prefetch_related(
            'images', 'videos', 'documents', 'categories', 'tags', 'variants'
        ),
        id=product_id
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_basic':
            product.name = request.POST.get('name')
            product.description = request.POST.get('description', '')
            product.short_description = request.POST.get('short_description', '')
            product.status = request.POST.get('status')
            product.is_active = request.POST.get('is_active') == 'on'
            product.is_featured = request.POST.get('is_featured') == 'on'

            brand_id = request.POST.get('brand')
            product.brand_id = brand_id if brand_id else None

            product.save()

            # Update categories
            category_ids = request.POST.getlist('categories')
            product.categories.set(category_ids)

            messages.success(request, 'Product updated successfully!')

        elif action == 'add_image':
            if 'image' in request.FILES:
                is_primary = not product.images.exists()  # First image is primary
                ProductImage.objects.create(
                    product=product,
                    image=request.FILES['image'],
                    alt_text=request.POST.get('alt_text', ''),
                    is_primary=is_primary
                )
                messages.success(request, 'Image added!')

        elif action == 'delete_image':
            image_id = request.POST.get('image_id')
            ProductImage.objects.filter(id=image_id, product=product).delete()
            messages.success(request, 'Image deleted!')

        return redirect('product_edit', product_id=product_id)

    # GET - show edit form
    categories = Category.objects.filter(is_active=True).order_by('name')
    brands = Brand.objects.filter(is_active=True).order_by('name')
    tags = Tag.objects.filter(is_active=True).order_by('name')

    context = {
        'product': product,
        'categories': categories,
        'brands': brands,
        'tags': tags,
        'product_types': Product.TYPE_CHOICES,
        'status_choices': Product._meta.get_field('status').choices,
    }

    return render(request, 'ecommerce/products/edit.html', context)


# ============================================================================
# PRODUCT VARIANTS
# ============================================================================

@login_required
@permission_required('catalog.change_product', raise_exception=True)
def product_variants(request, product_id):
    """Manage product variants"""

    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_variant':
            sku = request.POST.get('sku')
            price = request.POST.get('price')
            stock = request.POST.get('stock_quantity', 0)

            variant = ProductVariant.objects.create(
                product=product,
                sku=sku,
                price=price,
                stock_quantity=stock
            )

            # Add attribute values
            option_value_ids = request.POST.getlist('option_values')
            if option_value_ids:
                variant.option_values.set(option_value_ids)

            messages.success(request, f'Variant "{sku}" created!')

        elif action == 'update_variant':
            variant_id = request.POST.get('variant_id')
            variant = get_object_or_404(ProductVariant, id=variant_id, product=product)

            variant.price = request.POST.get('price')
            variant.stock_quantity = request.POST.get('stock_quantity', 0)
            variant.is_active = request.POST.get('is_active') == 'on'
            variant.save()

            messages.success(request, 'Variant updated!')

        return redirect('product_variants', product_id=product_id)

    # GET
    variants = product.variants.prefetch_related('option_values__attribute').order_by('sku')
    variant_attributes = Attribute.objects.filter(is_variant_option=True).prefetch_related('values')

    context = {
        'product': product,
        'variants': variants,
        'variant_attributes': variant_attributes,
    }

    return render(request, 'ecommerce/products/variants.html', context)


# ============================================================================
# INVENTORY
# ============================================================================

@login_required
@permission_required('inventory.view_inventorylocation', raise_exception=True)
def inventory_list(request):
    """List all inventory with filters"""

    inventory = InventoryLocation.objects.select_related(
        'warehouse', 'variant__product'
    ).filter(is_active=True)

    # Filters
    search = request.GET.get('search')
    if search:
        inventory = inventory.filter(
            Q(variant__sku__icontains=search) |
            Q(variant__product__name__icontains=search)
        )

    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        inventory = inventory.filter(warehouse_id=warehouse_id)

    low_stock = request.GET.get('low_stock')
    if low_stock:
        inventory = inventory.filter(quantity__lte=F('reorder_point'))

    # Pagination
    paginator = Paginator(inventory, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    warehouses = Warehouse.objects.filter(is_active=True).order_by('name')

    context = {
        'page_obj': page_obj,
        'warehouses': warehouses,
    }

    return render(request, 'ecommerce/inventory/list.html', context)


@login_required
@permission_required('inventory.change_inventorylocation', raise_exception=True)
def inventory_adjust(request, location_id):
    """Adjust inventory quantity"""

    location = get_object_or_404(InventoryLocation, id=location_id)

    if request.method == 'POST':
        adjustment = int(request.POST.get('adjustment', 0))
        movement_type = request.POST.get('movement_type')
        notes = request.POST.get('notes', '')

        quantity_before = location.quantity
        location.quantity += adjustment
        location.save()

        # Log the movement
        StockMovement.objects.create(
            variant=location.variant,
            warehouse=location.warehouse,
            movement_type=movement_type,
            quantity=adjustment,
            quantity_before=quantity_before,
            quantity_after=location.quantity,
            notes=notes,
            created_by=request.user
        )

        messages.success(request, f'Inventory adjusted by {adjustment:+d}')
        return redirect('inventory_list')

    context = {
        'location': location,
        'movement_types': StockMovement.MOVEMENT_TYPES,
    }

    return render(request, 'ecommerce/inventory/adjust.html', context)


# ============================================================================
# PRICING & PROMOTIONS
# ============================================================================

@login_required
@permission_required('pricing.view_promotion', raise_exception=True)
def promotion_list(request):
    """List all promotions"""

    promotions = Promotion.objects.all().order_by('-starts_at')

    # Filter by status
    status = request.GET.get('status')
    now = timezone.now()

    if status == 'active':
        promotions = promotions.filter(
            is_active=True,
            starts_at__lte=now,
            ends_at__gte=now
        )
    elif status == 'scheduled':
        promotions = promotions.filter(starts_at__gt=now)
    elif status == 'expired':
        promotions = promotions.filter(ends_at__lt=now)

    paginator = Paginator(promotions, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
    }

    return render(request, 'ecommerce/promotions/list.html', context)


@login_required
@permission_required('pricing.add_promotion', raise_exception=True)
def promotion_create(request):
    """Create new promotion"""

    if request.method == 'POST':
        name = request.POST.get('name')
        promotion_type = request.POST.get('promotion_type')
        discount_value = request.POST.get('discount_value')
        starts_at = request.POST.get('starts_at')
        ends_at = request.POST.get('ends_at')

        promotion = Promotion.objects.create(
            name=name,
            promotion_type=promotion_type,
            discount_value=discount_value,
            starts_at=starts_at,
            ends_at=ends_at if ends_at else None,
            description=request.POST.get('description', ''),
            is_active=request.POST.get('is_active') == 'on'
        )

        messages.success(request, f'Promotion "{name}" created!')
        return redirect('promotion_edit', promotion_id=promotion.id)

    context = {
        'promotion_types': Promotion.PROMOTION_TYPES,
    }

    return render(request, 'ecommerce/promotions/create.html', context)


@login_required
@permission_required('pricing.change_promotion', raise_exception=True)
def promotion_edit(request, promotion_id):
    """Edit promotion"""

    promotion = get_object_or_404(Promotion, id=promotion_id)

    if request.method == 'POST':
        promotion.name = request.POST.get('name')
        promotion.description = request.POST.get('description', '')
        promotion.discount_value = request.POST.get('discount_value')
        promotion.is_active = request.POST.get('is_active') == 'on'
        promotion.save()

        messages.success(request, 'Promotion updated!')
        return redirect('promotion_list')

    context = {
        'promotion': promotion,
        'promotion_types': Promotion.PROMOTION_TYPES,
    }

    return render(request, 'ecommerce/promotions/edit.html', context)


# ============================================================================
# COUPONS
# ============================================================================

@login_required
@permission_required('pricing.view_coupon', raise_exception=True)
def coupon_list(request):
    """List all coupons"""

    coupons = Coupon.objects.all().order_by('-created_at')

    paginator = Paginator(coupons, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
    }

    return render(request, 'ecommerce/coupons/list.html', context)


@login_required
@permission_required('pricing.add_coupon', raise_exception=True)
def coupon_create(request):
    """Create new coupon"""

    if request.method == 'POST':
        code = request.POST.get('code').upper()
        discount_type = request.POST.get('discount_type')
        discount_value = request.POST.get('discount_value')
        valid_from = request.POST.get('valid_from')
        valid_until = request.POST.get('valid_until')

        coupon = Coupon.objects.create(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            valid_from=valid_from,
            valid_until=valid_until if valid_until else None,
            description=request.POST.get('description', ''),
            is_active=request.POST.get('is_active') == 'on'
        )

        messages.success(request, f'Coupon "{code}" created!')
        return redirect('coupon_list')

    context = {
        'discount_types': Coupon.DISCOUNT_TYPES,
    }

    return render(request, 'ecommerce/coupons/create.html', context)


# ============================================================================
# REVIEWS
# ============================================================================

@login_required
@permission_required('reviews.view_review', raise_exception=True)
def review_list(request):
    """List all reviews for moderation"""

    reviews = Review.objects.select_related('product', 'user').order_by('-created_at')

    # Filter by status
    status = request.GET.get('status')
    if status:
        reviews = reviews.filter(status=status)

    paginator = Paginator(reviews, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
    }

    return render(request, 'ecommerce/reviews/list.html', context)


@login_required
@permission_required('reviews.change_review', raise_exception=True)
def review_moderate(request, review_id):
    """Moderate a review"""

    review = get_object_or_404(Review, id=review_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            review.status = 'approved'
            review.moderated_by = request.user
            review.moderated_at = timezone.now()
            review.save()
            messages.success(request, 'Review approved!')

        elif action == 'reject':
            review.status = 'rejected'
            review.moderation_note = request.POST.get('note', '')
            review.moderated_by = request.user
            review.moderated_at = timezone.now()
            review.save()
            messages.success(request, 'Review rejected!')

        return redirect('review_list')

    context = {
        'review': review,
    }

    return render(request, 'ecommerce/reviews/moderate.html', context)



from system.account.models import PlatformUser
from system.core.models import Shop,Domain
PlatformUser.objects.all()
Shop.objects.all()
Domain.objects.all()
