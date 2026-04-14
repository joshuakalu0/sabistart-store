# Dynamic Dashboard URL System

## Overview

Production-grade dynamic dashboard URL structure with database-driven prefix for security and isolation.

## Architecture

### URL Structure

```
Public Store:
/                           → Storefront home
/products/                  → Product catalog
/cart/                      → Shopping cart

Dashboard (Dynamic):
/dashboard/<prefix>/                    → Dashboard home
/dashboard/<prefix>/products/           → Product management
/dashboard/<prefix>/products/create/    → Create product
```

### How It Works

1. **StoreSettings Model** (core/models.py)
   - Stores unique dashboard_prefix per tenant
   - Auto-generates secure random prefix on creation
   - Singleton pattern: one settings record per store

2. **Decorator** (dashboard/decorators.py)
   - `@dashboard_prefix_required`
   - Validates URL prefix against database
   - Returns 404 if prefix doesn't match
   - Attaches settings to request object

3. **URL Configuration**
   - Main: `path('dashboard/', include('dashboard.urls'))`
   - Dashboard: `path('<str:prefix>/', ...)`
   - Captures prefix as URL parameter

## Security Features

✅ **Dynamic URLs** - Prefix changes invalidate old URLs
✅ **Database validation** - Every request checks prefix
✅ **404 on mismatch** - No information leakage
✅ **Tenant isolation** - Each store has unique prefix
✅ **Secure generation** - Uses secrets.token_urlsafe()

## Usage

### 1. Create Store Settings

```python
from core.models import StoreSettings

# Auto-creates with random prefix
settings = StoreSettings.get_settings()
print(settings.dashboard_prefix)  # e.g., 'x7h3k9'
```

### 2. Access Dashboard

```
Valid:   /dashboard/x7h3k9/
Invalid: /dashboard/
Invalid: /dashboard/wrongprefix/
```

### 3. Create Dashboard Views

```python
from django.contrib.auth.decorators import login_required
from dashboard.decorators import dashboard_prefix_required

@login_required
@dashboard_prefix_required
def my_view(request, prefix):
    # prefix is validated automatically
    # request.dashboard_settings is available
    return render(request, 'template.html', {'prefix': prefix})
```

### 4. Generate URLs in Templates

```django
<a href="{% url 'dashboard:dashboard_home:home' prefix %}">Home</a>
<a href="{% url 'dashboard:dashboard_products:list' prefix %}">Products</a>
```

## Changing the Prefix

```python
from core.models import StoreSettings

settings = StoreSettings.get_settings()
settings.dashboard_prefix = StoreSettings.generate_prefix()
settings.save()

# All old URLs now return 404
# New URL: /dashboard/<new_prefix>/
```

## File Structure

```
dashboard/
├── __init__.py
├── decorators.py              # Prefix validation decorator
├── urls.py                    # Main dashboard URLs
├── home/
│   ├── views.py
│   ├── urls.py
│   └── templates/
│       └── dashboard/
│           └── home/
│               └── index.html
└── products/
    ├── views.py
    ├── urls.py
    └── templates/
        └── dashboard/
            └── products/
                ├── list.html
                └── create.html
```

## Integration with Main URLs

```python
# sabistart_store/urls.py
from django.urls import path, include

urlpatterns = [
    # Public storefront
    path('', include('storefront.urls')),
    
    # Dynamic dashboard
    path('dashboard/', include('dashboard.urls')),
]
```

## Scalability Notes

1. **Caching**: Cache StoreSettings to reduce DB queries
2. **Middleware**: Consider middleware for global prefix validation
3. **Logging**: Log invalid prefix attempts for security monitoring
4. **Rate limiting**: Add rate limiting to prevent brute force
5. **Prefix rotation**: Implement scheduled prefix rotation policy

## Best Practices

- ✅ Always use `@dashboard_prefix_required` on dashboard views
- ✅ Pass `prefix` to all dashboard templates
- ✅ Use `{% url %}` tags with prefix parameter
- ✅ Never hardcode dashboard URLs
- ✅ Rotate prefix periodically for security
- ✅ Log all dashboard access attempts

## Example: Complete View

```python
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from dashboard.decorators import dashboard_prefix_required

@login_required
@dashboard_prefix_required
def dashboard_settings(request, prefix):
    \"\"\"Dashboard settings page with prefix management.\"\"\"
    
    if request.method == 'POST':
        # Regenerate prefix
        settings = request.dashboard_settings
        old_prefix = settings.dashboard_prefix
        settings.dashboard_prefix = StoreSettings.generate_prefix()
        settings.save()
        
        messages.success(request, f'Dashboard URL updated!')
        return redirect('dashboard:dashboard_home:home', prefix=settings.dashboard_prefix)
    
    context = {
        'prefix': prefix,
        'settings': request.dashboard_settings
    }
    return render(request, 'dashboard/settings.html', context)
```
