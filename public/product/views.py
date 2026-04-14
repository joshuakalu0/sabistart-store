from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
from .models import (
    AttributeGroup, Attribute, AttributeValue, Product, ProductImage,
    ProductVideo, ProductAttributeValue, ProductVariant, VariantImage
)
from .forms import (
    AttributeGroupForm, AttributeForm, AttributeValueForm, ProductForm,
    ProductImageForm, ProductVideoForm,
    ProductAttributeValueForm, ProductVariantForm, VariantImageForm,
    ProductImageFormSet, ProductVideoFormSet,
    ProductAttributeValueFormSet, ProductVariantFormSet, VariantImageFormSet
)
from dashboard.decorators import dashboard_prefix_required
import json


@login_required
@dashboard_prefix_required
def attribute_group_list(request, prefix):
    search_query = request.GET.get('search', '')
    groups = AttributeGroup.objects.all()

    if search_query:
        groups = groups.filter(Q(name__icontains=search_query) | Q(
            description__icontains=search_query))

    paginator = Paginator(groups, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'dashboard/products/attribute_groups/list.html', {
        'page_obj': page_obj, 'search_query': search_query, 'prefix': prefix, 'title': 'Attribute Groups'
    })


@login_required
@dashboard_prefix_required
def attribute_group_create(request, prefix):
    if request.method == 'POST':
        form = AttributeGroupForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    group = form.save()
                    messages.success(
                        request, f'Attribute group "{group.name}" created successfully.')
                    return redirect('product:attribute_group_list', prefix=prefix)
            except Exception as e:
                messages.error(
                    request, f'Error creating attribute group: {str(e)}')
    else:
        form = AttributeGroupForm()

    return render(request, 'dashboard/products/attribute_groups/form.html', {
        'form': form, 'prefix': prefix, 'title': 'Create Attribute Group', 'action': 'Create'
    })


@login_required
@dashboard_prefix_required
def attribute_group_edit(request, prefix, pk):
    group = get_object_or_404(AttributeGroup, pk=pk)

    if request.method == 'POST':
        form = AttributeGroupForm(request.POST, instance=group)
        if form.is_valid():
            try:
                with transaction.atomic():
                    group = form.save()
                    messages.success(
                        request, f'Attribute group "{group.name}" updated successfully.')
                    return redirect('product:attribute_group_list', prefix=prefix)
            except Exception as e:
                messages.error(
                    request, f'Error updating attribute group: {str(e)}')
    else:
        form = AttributeGroupForm(instance=group)

    return render(request, 'dashboard/products/attribute_groups/form.html', {
        'form': form, 'group': group, 'prefix': prefix, 'title': f'Edit {group.name}', 'action': 'Update'
    })


@login_required
@dashboard_prefix_required
def attribute_group_delete(request, prefix, pk):
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

    return redirect('product:attribute_group_list', prefix=prefix)


@login_required
@dashboard_prefix_required
def attribute_list(request, prefix):
    search_query = request.GET.get('search', '')
    group_filter = request.GET.get('group', '')
    type_filter = request.GET.get('type', '')

    attributes = Attribute.objects.select_related('group')

    if search_query:
        attributes = attributes.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query))
    if group_filter:
        attributes = attributes.filter(group_id=group_filter)
    if type_filter:
        attributes = attributes.filter(attribute_type=type_filter)

    paginator = Paginator(attributes, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'dashboard/products/attributes/list.html', {
        'page_obj': page_obj, 'search_query': search_query, 'group_filter': group_filter,
        'type_filter': type_filter, 'groups': AttributeGroup.objects.all(),
        'types': Attribute.TYPE_CHOICES, 'prefix': prefix, 'title': 'Attributes'
    })


@login_required
@dashboard_prefix_required
def attribute_create(request, prefix):
    if request.method == 'POST':
        form = AttributeForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    attribute = form.save()
                    messages.success(
                        request, f'Attribute "{attribute.name}" created successfully.')
                    return redirect('product:attribute_list', prefix=prefix)
            except Exception as e:
                messages.error(request, f'Error creating attribute: {str(e)}')
    else:
        form = AttributeForm()

    return render(request, 'dashboard/products/attributes/form.html', {
        'form': form, 'prefix': prefix, 'title': 'Create Attribute', 'action': 'Create'
    })


@login_required
@dashboard_prefix_required
def attribute_edit(request, prefix, pk):
    attribute = get_object_or_404(Attribute, pk=pk)

    if request.method == 'POST':
        form = AttributeForm(request.POST, instance=attribute)
        if form.is_valid():
            try:
                with transaction.atomic():
                    attribute = form.save()
                    messages.success(
                        request, f'Attribute "{attribute.name}" updated successfully.')
                    return redirect('product:attribute_list', prefix=prefix)
            except Exception as e:
                messages.error(request, f'Error updating attribute: {str(e)}')
    else:
        form = AttributeForm(instance=attribute)

    return render(request, 'dashboard/products/attributes/form.html', {
        'form': form, 'attribute': attribute, 'prefix': prefix, 'title': f'Edit {attribute.name}', 'action': 'Update'
    })


@login_required
@dashboard_prefix_required
def attribute_delete(request, prefix, pk):
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

    return redirect('product:attribute_list', prefix=prefix)


@login_required
@dashboard_prefix_required
def product_list(request, prefix):
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')

    products = Product.objects.select_related(
        'brand').prefetch_related('categories', 'tags')

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

    return render(request, 'dashboard/products/list.html', {
        'page_obj': page_obj, 'search_query': search_query, 'status_filter': status_filter,
        'type_filter': type_filter, 'categories': Category.objects.all(), 'brands': Brand.objects.all(),
        'statuses': Product._meta.get_field('status').choices, 'types': Product.TYPE_CHOICES,
        'prefix': prefix, 'title': 'Products'
    })


@login_required
@dashboard_prefix_required
def product_create(request, prefix):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        image_formset = ProductImageFormSet(request.POST, request.FILES)

        if form.is_valid() and image_formset.is_valid():
            try:
                with transaction.atomic():
                    product = form.save()
                    image_formset.instance = product
                    image_formset.save()
                    messages.success(
                        request, f'Product "{product.name}" created successfully.')
                    return redirect('product:product_list', prefix=prefix)
            except Exception as e:
                messages.error(request, f'Error creating product: {str(e)}')
    else:
        form = ProductForm()
        image_formset = ProductImageFormSet()

    return render(request, 'dashboard/products/create.html', {
        'form': form, 'image_formset': image_formset, 'prefix': prefix,
        'title': 'Create Product', 'action': 'Create'
    })


@login_required
@dashboard_prefix_required
def product_edit(request, prefix, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        image_formset = ProductImageFormSet(
            request.POST, request.FILES, instance=product)

        if form.is_valid() and image_formset.is_valid():
            try:
                with transaction.atomic():
                    product = form.save()
                    image_formset.save()
                    messages.success(
                        request, f'Product "{product.name}" updated successfully.')
                    return redirect('product:product_list', prefix=prefix)
            except Exception as e:
                messages.error(request, f'Error updating product: {str(e)}')
    else:
        form = ProductForm(instance=product)
        image_formset = ProductImageFormSet(instance=product)

    return render(request, 'dashboard/products/form.html', {
        'form': form, 'image_formset': image_formset, 'product': product, 'prefix': prefix,
        'title': f'Edit {product.name}', 'action': 'Update'
    })


@login_required
@dashboard_prefix_required
def product_delete(request, prefix, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                product_name = product.name
                product.delete()
                messages.success(
                    request, f'Product "{product_name}" deleted successfully.')
        except Exception as e:
            messages.error(request, f'Error deleting product: {str(e)}')

    return redirect('product:product_list', prefix=prefix)


@require_http_methods(["GET"])
def generate_slug(request):
    name = request.GET.get('name', '')
    slug = slugify(name)
    return JsonResponse({'slug': slug})
