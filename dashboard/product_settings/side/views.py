

@login_required
@dashboard_prefix_required
def product_create(request, prefix):
    # Check if editing existing product
    edit_id = request.GET.get('edit')
    product = get_object_or_404(Product, pk=edit_id) if edit_id else None

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        image_formset = ProductImageFormSet(
            request.POST, request.FILES, instance=product)

        if form.is_valid():
            # if form.is_valid() and image_formset.is_valid():
            try:
                with transaction.atomic():
                    product = form.save()
                    image_formset.instance = product
                    image_formset.save()

                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'product_id': product.id,
                            'redirect_url': f'/{prefix}/products/'
                        })

                    action = 'updated' if edit_id else 'created'
                    messages.success(
                        request, f'Product "{product.name}" {action} successfully.')
                    return redirect('dashboard:product_settings:product_list', prefix=prefix)
            except Exception as e:
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'errors': {'__all__': [str(e)]}
                    })
                messages.error(request, f'Error saving product: {str(e)}')
        else:
            if is_ajax:
                errors = {}
                if form.errors:
                    errors.update(form.errors)
                if image_formset.errors:
                    for i, form_errors in enumerate(image_formset.errors):
                        if form_errors:
                            errors[f'image_{i}'] = form_errors
                return JsonResponse({
                    'success': False,
                    'errors': errors
                })
    else:
        form = ProductForm(instance=product)
        image_formset = ProductImageFormSet(instance=product)

    # Prepare data for JavaScript
    from public.category.models import Category, Tag
    categories = Category.objects.all()
    tags = Tag.objects.all()

    categories_json = json.dumps(
        [{'id': str(c.id), 'name': c.name} for c in categories])
    tags_json = json.dumps([{'id': str(t.id), 'name': t.name} for t in tags])

    return render(request, 'dashboard/products/create.html', {
        'form': form, 'image_formset': image_formset, 'prefix': prefix,
        'title': f'Edit {product.name}' if product else 'Create Product',
        'action': 'Update' if product else 'Create',
        'product': product,
        'sidebar': main_sidebar(prefix),
        'categories_json': categories_json,
        'tags': tags_json,
        'attributes': json.dumps([]),
        'is_edit': bool(product),
    })


@login_required
@dashboard_prefix_required
def product_edit(request, prefix, pk):
    product = get_object_or_404(Product, pk=pk)
    print(product.images, 'lidt')
    form = ProductForm(instance=product)
    image_formset = ProductImageFormSet(instance=product)

    # Prepare specifications data
    specifications = product.specifications or {}

    # Prepare features data
    features = product.features or []
    print(f"Features data: {features}")
    print(f"Features type: {type(features)}")

    # Prepare data for JavaScript
    from public.category.models import Category, Tag
    categories = Category.objects.all()
    tags = Tag.objects.all()

    categories_json = json.dumps(
        [{'id': str(c.id), 'name': c.name} for c in categories])
    tags_json = json.dumps([{'id': str(t.id), 'name': t.name} for t in tags])

    return render(request, 'dashboard/products/create.html', {
        'form': form, 'image_formset': image_formset, 'product': product, 'prefix': prefix,
        'title': f'Edit {product.name}', 'action': 'Update',
        'specifications': specifications, 'features': features, 'sidebar': main_sidebar(prefix),
        'categories_json': categories_json,
        'tags': tags_json,
        'attributes': json.dumps([]),
        'is_edit': True,
    })


@login_required
@dashboard_prefix_required
def product_update(request, prefix, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        print(request.FILES)
        image_formset = ProductImageFormSet(
            request.POST, request.FILES, instance=product)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save main product form
                    product = form.save()

                    # Save image formset only if valid
                    if image_formset.is_valid():
                        image_formset.save()
                    else:
                        print(f"Image formset errors: {image_formset.errors}")
                        print(
                            f"Image formset non_form_errors: {image_formset.non_form_errors()}")

                    # Handle specifications from form data
                    spec_labels = request.POST.getlist('spec_label')
                    spec_values = request.POST.getlist('spec_value')
                    if spec_labels and spec_values:
                        specifications = {}
                        for label, value in zip(spec_labels, spec_values):
                            if label.strip() and value.strip():
                                specifications[label.strip()] = value.strip()
                        if specifications:
                            product.specifications = specifications

                    # Handle features from form data
                    # Collect features from existing displayed features
                    features_list = []
                    feature_inputs = request.POST.getlist('existing_features')
                    for feature in feature_inputs:
                        if feature.strip():
                            features_list.append(feature.strip())

                    # Also handle new features from input
                    new_features = request.POST.get('new_features', '')
                    if new_features:
                        features_list.extend(
                            [f.strip() for f in new_features.split(',') if f.strip()])

                    if features_list:
                        product.features = features_list

                    # Save final product with specifications and features
                    product.save()

                    return JsonResponse({'success': True, 'message': 'Product updated successfully'})
            except Exception as e:
                return JsonResponse({'success': False, 'errors': {'__all__': [str(e)]}})
        else:
            errors = {}
            if form.errors:
                errors.update(form.errors)
            if image_formset.errors:
                for i, form_errors in enumerate(image_formset.errors):
                    if form_errors:
                        errors[f'image_{i}'] = form_errors
            return JsonResponse({'success': False, 'errors': errors})

    return JsonResponse({'success': False, 'errors': {'__all__': ['Invalid request method']}})
