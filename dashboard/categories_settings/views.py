from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from dashboard.decorators import dashboard_prefix_required
from public.category.models import Category, Tag, Brand
from public.category.forms import CategoryForm, TagForm, BrandForm
from dashboard.sidebar_utiles import main_sidebar, get_settings_sidebar, get_sidebar_with_active, get_sub_sidebar_with_active

from django.shortcuts import render, get_object_or_404
from django.utils.text import slugify


@login_required
@dashboard_prefix_required
def category_list(request, prefix):
    """Category list page - requires valid prefix."""
    categories = Category.objects.filter(is_active=True)
    context = {
        'prefix': prefix,
        'page_title': 'Categories',
        'active_menu': 'categories',
        'store_name': 'My Store',
        'categories': categories,
        'sidebar':  main_sidebar(prefix),
        # 'sub_sidebar': get_settings_sidebar ,
    }
    return render(request, 'dashboard/category/list.html', context)


@login_required
@dashboard_prefix_required
def category_create(request, prefix):
    """Category create page - requires valid prefix."""
    user = request.user
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # form.save(created_by=request.user, updated_by=request.user)
                    category = form.save(commit=False)
                    category.created_by = user
                    category.updated_by = user
                    category.save()
                messages.success(request, 'Category created successfully!')
                return redirect(reverse('dashboard:dashboard_categories:list', args=[prefix]))
            except Exception as e:
                print(e)
                messages.error(request, f'Error creating category: {str(e)}')
        else:
            print(form.errors)
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CategoryForm()
    form = CategoryForm()

    context = {
        'prefix': prefix,
        'page_title': 'Create Category',
        'active_menu': 'categories',
        'store_name': 'My Store',
        'form':  form,
        # 'form': None,
        'sidebar': main_sidebar(prefix),  # main_sidebar,
        'sub_sidebar': None  # get_settings_sidebar,
    }
    return render(request, 'dashboard/category/create.html', context)


@login_required
@dashboard_prefix_required
def category_edit(request, prefix, category_id):
    """Category edit page - requires valid prefix."""
    category = Category.objects.get(id=category_id)

    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES, instance=category)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save(updated_by=request.user)
                messages.success(request, 'Category updated successfully!')
                return redirect(reverse('dashboard:dashboard_categories:list', args=[prefix]))
            except Exception as e:
                messages.error(request, f'Error updating category: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CategoryForm(instance=category)

    context = {
        'prefix': prefix,
        'page_title': 'Edit Category',
        'active_menu': 'categories',
        'store_name': 'My Store',
        'form': form,
        'category': category if category else {},
        'sub_sidebar': None,
        'sidebar': main_sidebar(prefix),
        'edit_url': reverse('dashboard:dashboard_categories:edit', kwargs=({'prefix': prefix, 'category_id': category_id})),
    }
    return render(request, 'dashboard/category/create.html', context)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def category_delete(request, prefix, category_id):
    """Category delete endpoint - requires valid prefix."""
    try:
        category = Category.objects.get(id=category_id)
        category.delete()
        messages.success(request, 'Category deleted successfully!')
        return redirect(reverse('dashboard:dashboard_categories:list', args=[prefix]))
    except Category.DoesNotExist:
        messages.error(request, 'Category not found!')
        return redirect(reverse('dashboard:dashboard_categories:list', args=[prefix]))
    except Exception as e:
        messages.error(request, f'Error deleting category: {str(e)}')
        return redirect(reverse('dashboard:dashboard_categories:list', args=[prefix]))


# Tag views
@login_required
@dashboard_prefix_required
def tag_list(request, prefix):
    """Tag list page - requires valid prefix."""
    tags = Tag.objects.filter(is_active=True)
    context = {
        'prefix': prefix,
        'page_title': 'Tags',
        'active_menu': 'tags',
        'store_name': 'My Store',
        'tags': tags,
        'sidebar': main_sidebar(prefix),  # main_sidebar,
        'sub_sidebar': None  # get_settings_sidebar,
    }
    return render(request, 'dashboard/category/tag_list.html', context)


@login_required
@dashboard_prefix_required
def tag_create(request, prefix):
    """Tag create page - requires valid prefix."""
    if request.method == 'POST':
        form = TagForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save(created_by=request.user, updated_by=request.user)
                messages.success(request, 'Tag created successfully!')
                return redirect(reverse('dashboard:dashboard_categories:tag_list', args=[prefix]))
            except Exception as e:
                print(e)
                messages.error(request, f'Error creating tag: {str(e)}')
        else:
            print(e)
            messages.error(request, 'Please correct the errors below.')
    else:
        form = TagForm()

    context = {
        'prefix': prefix,
        'page_title': 'Create Tag',
        'active_menu': 'tags',
        'store_name': 'My Store',
        'form': form,
        'sidebar': main_sidebar(prefix),  # main_sidebar,
        'sub_sidebar': None  # get_settings_sidebar,
    }
    return render(request, 'dashboard/category/tag_create.html', context)


def ajax_create_tag(request, prefix):
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
@dashboard_prefix_required
def tag_edit(request, prefix, tag_id):
    """Tag edit page - requires valid prefix."""
    tag = Tag.objects.get(id=tag_id)

    if request.method == 'POST':
        form = TagForm(request.POST, request.FILES, instance=tag)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save(updated_by=request.user)
                messages.success(request, 'Tag updated successfully!')
                return redirect(reverse('dashboard:dashboard_categories:tag_list', args=[prefix]))
            except Exception as e:
                messages.error(request, f'Error updating tag: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = TagForm(instance=tag)

    context = {
        'prefix': prefix,
        'page_title': 'Edit Tag',
        'active_menu': 'tags',
        'store_name': 'My Store',
        'form': form,
        'tag': tag,
        'sidebar': main_sidebar(prefix),  # main_sidebar,
        'sub_sidebar': None  # get_settings_sidebar,
    }
    return render(request, 'dashboard/category/tag_edit.html', context)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def tag_delete(request, prefix, tag_id):
    """Tag delete endpoint - requires valid prefix."""
    try:
        tag = Tag.objects.get(id=tag_id)
        tag.delete()
        messages.success(request, 'Tag deleted successfully!')
        return redirect(reverse('dashboard:dashboard_categories:tag_list', args=[prefix]))
    except Tag.DoesNotExist:
        messages.error(request, 'Tag not found!')
        return redirect(reverse('dashboard:dashboard_categories:tag_list', args=[prefix]))
    except Exception as e:
        messages.error(request, f'Error deleting tag: {str(e)}')
        return redirect(reverse('dashboard:dashboard_categories:tag_list', args=[prefix]))


# Brand views
@login_required
@dashboard_prefix_required
def brand_list(request, prefix):
    """Brand list page - requires valid prefix."""
    brands = Brand.objects.filter(is_active=True)
    context = {
        'prefix': prefix,
        'page_title': 'Brands',
        'active_menu': 'brands',
        'store_name': 'My Store',
        'brands': brands,
        'sidebar': main_sidebar(prefix),  # main_sidebar,
        'sub_sidebar': None  # get_settings_sidebar,
    }
    return render(request, 'dashboard/category/brand_list.html', context)


@login_required
# @dashboard_prefix_required
def brand_create(request, prefix):
    """Brand create page - requires valid prefix."""
    user = request.user
    if request.method == 'POST':
        form = BrandForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    brand = form.save(commit=False)
                    brand.created_by = user
                    brand.updated_by = user
                    brand.save()
                    # form.save(created_by=request.user, updated_by=request.user)
                messages.success(request, 'Brand created successfully!')
                return redirect(reverse('dashboard:dashboard_categories:brand_list', args=[prefix]))
            except Exception as e:
                messages.error(request, f'Error creating brand: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BrandForm()

    context = {
        'prefix': prefix,
        'page_title': 'Create Brand',
        'active_menu': 'brands',
        'store_name': 'My Store',
        'form': form,
        'sidebar': main_sidebar(prefix),  # main_sidebar,
        'sub_sidebar': None  # get_settings_sidebar,
    }
    return render(request, 'dashboard/category/brand_create.html', context)


@login_required
@dashboard_prefix_required
def brand_edit(request, prefix, brand_id):
    """Brand edit page - requires valid prefix."""
    brand = Brand.objects.get(id=brand_id)

    if request.method == 'POST':
        form = BrandForm(request.POST, request.FILES, instance=brand)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save(updated_by=request.user)
                messages.success(request, 'Brand updated successfully!')
                return redirect(reverse('dashboard:dashboard_categories:brand_list', args=[prefix]))
            except Exception as e:
                messages.error(request, f'Error updating brand: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BrandForm(instance=brand)

    context = {
        'prefix': prefix,
        'page_title': 'Edit Brand',
        'active_menu': 'brands',
        'store_name': 'My Store',
        'form': form,
        'brand': brand,
        'sidebar': main_sidebar(prefix),  # main_sidebar,
        'sub_sidebar': None  # get_settings_sidebar,
    }
    return render(request, 'dashboard/category/brand_edit.html', context)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def brand_delete(request, prefix, brand_id):
    """Brand delete endpoint - requires valid prefix."""
    try:
        brand = Brand.objects.get(id=brand_id)
        brand.delete()
        messages.success(request, 'Brand deleted successfully!')
        return redirect(reverse('dashboard:dashboard_categories:brand_list', args=[prefix]))
    except Brand.DoesNotExist:
        messages.error(request, 'Brand not found!')
        return redirect(reverse('dashboard:dashboard_categories:brand_list', args=[prefix]))
    except Exception as e:
        messages.error(request, f'Error deleting brand: {str(e)}')
        return redirect(reverse('dashboard:dashboard_categories:brand_list', args=[prefix]))


@login_required
@dashboard_prefix_required
@require_http_methods(["GET"])
def category_details(request, prefix, category_id):
    """Category details endpoint for modal - requires valid prefix."""
    category = get_object_or_404(Category, id=category_id)

    # Render category details HTML snippet
    context = {"category": category}
    return render(request, "dashboard/category/partials/details.html", context)


@login_required
@dashboard_prefix_required
@require_http_methods(["GET"])
def tag_details(request, prefix, tag_id):
    """Tag details endpoint for modal - requires valid prefix."""
    tag = get_object_or_404(Tag, id=tag_id)

    # Render tag details HTML snippet
    context = {"tag": tag}
    return render(request, "dashboard/category/partials/tag_details.html", context)


@login_required
@dashboard_prefix_required
@require_http_methods(["GET"])
def brand_details(request, prefix, brand_id):
    """Brand details endpoint for modal - requires valid prefix."""
    brand = get_object_or_404(Brand, id=brand_id)

    # Render brand details HTML snippet
    context = {"brand": brand}
    return render(request, "dashboard/category/partials/brand_details.html", context)
