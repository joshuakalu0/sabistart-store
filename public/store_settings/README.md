# Enterprise Store Settings System

## Overview

A modular, scalable settings architecture for multi-tenant e-commerce stores. Each settings category is isolated in its own model for maximum flexibility and maintainability.

## Architecture

### Design Principles

1. **Modular**: Each settings category is a separate model
2. **Singleton Pattern**: One settings record per tenant per category
3. **Extensible**: Add new settings modules without refactoring
4. **Normalized**: Clean data structure with proper relationships
5. **Production-Ready**: UUID keys, timestamps, indexes, validators

## Settings Modules

### 1. GeneralSettings
**Purpose**: Core store identity and operational configuration

**Key Fields**:
- Store name, tagline, description
- Contact information (email, phone, address)
- Localization (language, currency, timezone)
- Store status (active, maintenance, closed)

**Use Cases**:
- Display store name in header
- Show contact info in footer
- Set default currency for pricing
- Enable maintenance mode

### 2. BrandingSettings
**Purpose**: Visual identity and theme customization

**Key Fields**:
- Logos (main, dark mode, favicon)
- Brand colors (primary, secondary, accent)
- Typography (heading font, body font)
- Layout preferences

**Use Cases**:
- Apply brand colors to storefront
- Display logo in header
- Set theme for customer experience

### 3. SEOSettings
**Purpose**: Search engine optimization and analytics

**Key Fields**:
- Custom domain configuration
- Meta tags (title, description, keywords)
- Open Graph settings for social sharing
- Analytics IDs (Google, Facebook)
- Robots.txt and sitemap settings

**Use Cases**:
- Improve search engine rankings
- Track visitor analytics
- Optimize social media sharing

### 4. PaymentSettings
**Purpose**: Payment gateway configuration

**Key Fields**:
- Test/live mode toggle
- Stripe integration (keys, webhook)
- PayPal integration
- Alternative methods (COD, bank transfer)
- Currency settings

**Use Cases**:
- Accept credit card payments
- Enable PayPal checkout
- Test payment flows safely

### 5. ShippingSettings
**Purpose**: Shipping and delivery configuration

**Key Fields**:
- Free shipping rules and thresholds
- Flat rate shipping
- Processing time
- Local pickup options
- Shipping restrictions

**Use Cases**:
- Calculate shipping costs
- Offer free shipping promotions
- Set delivery expectations

### 6. TaxSettings
**Purpose**: Tax calculation and compliance

**Key Fields**:
- Tax enabled/disabled
- Prices include tax toggle
- Default tax rate
- Tax on shipping
- Tax ID number

**Use Cases**:
- Calculate order taxes
- Display tax-inclusive prices
- Comply with tax regulations

### 7. NotificationSettings
**Purpose**: Email, SMS, and alert configuration

**Key Fields**:
- Email notification toggles
- Order status notifications
- Inventory alerts (low stock, out of stock)
- SMS settings
- Sender information

**Use Cases**:
- Send order confirmations
- Alert staff of new orders
- Notify customers of shipping

### 8. PolicySettings
**Purpose**: Legal and policy page content

**Key Fields**:
- Privacy policy
- Terms of service
- Refund policy
- Shipping policy
- Display toggles

**Use Cases**:
- Display legal policies
- Comply with regulations
- Set customer expectations

### 9. CheckoutSettings
**Purpose**: Checkout process configuration

**Key Fields**:
- Guest checkout toggle
- Required field settings
- Cart expiry
- Order notes
- Minimum order amount

**Use Cases**:
- Customize checkout flow
- Require/optional fields
- Set minimum order value

### 10. SecuritySettings
**Purpose**: Security and access control

**Key Fields**:
- Password policy rules
- Session timeout settings
- Two-factor authentication
- Login attempt limits
- GDPR compliance

**Use Cases**:
- Enforce strong passwords
- Enable 2FA for staff
- Comply with data protection laws

### 11. FeatureSettings
**Purpose**: Feature flags and integrations

**Key Fields**:
- Product reviews toggle
- Wishlist, compare features
- Gift cards, subscriptions
- Social login
- API access

**Use Cases**:
- Enable/disable features
- Control integrations
- Manage store capabilities

## Usage

### Retrieve Settings

```python
from store_settings.utils import (
    get_general_settings,
    get_branding_settings,
    get_all_settings
)

# Get specific settings
general = get_general_settings()
print(general.store_name)

# Get all settings
all_settings = get_all_settings()
```

### Update Settings

```python
from store_settings.models import GeneralSettings

settings = GeneralSettings.objects.first()
settings.store_name = "My Awesome Store"
settings.save()
```

### In Views

```python
from store_settings.utils import get_general_settings

def storefront_view(request):
    settings = get_general_settings()
    context = {
        'store_name': settings.store_name,
        'currency': settings.default_currency
    }
    return render(request, 'storefront.html', context)
```

### In Templates

```python
# Context processor (add to settings.py)
def store_settings(request):
    from store_settings.utils import get_all_settings
    return {'store_settings': get_all_settings()}
```

```django
<!-- In template -->
<h1>{{ store_settings.general.store_name }}</h1>
<div style="color: {{ store_settings.branding.primary_color }}">
    Welcome to our store!
</div>
```

## Database Schema

Each settings model:
- Uses UUID primary key
- Has created_at and updated_at timestamps
- Follows singleton pattern (one record per tenant)
- Includes proper indexes and validators

## Scalability

### Current Design
- ✅ Modular: Easy to add new settings categories
- ✅ Tenant-isolated: Each store has independent settings
- ✅ Performant: Indexed fields for fast queries
- ✅ Cacheable: Settings rarely change, perfect for caching

### Future Enhancements

1. **Caching Layer**
```python
from django.core.cache import cache

def get_general_settings():
    cache_key = 'general_settings'
    settings = cache.get(cache_key)
    if not settings:
        settings = GeneralSettings.objects.first()
        cache.set(cache_key, settings, 3600)  # 1 hour
    return settings
```

2. **Version History**
```python
class SettingsHistory(models.Model):
    setting_type = models.CharField(max_length=50)
    setting_id = models.UUIDField()
    changes = models.JSONField()
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL)
    changed_at = models.DateTimeField(auto_now_add=True)
```

3. **Settings Import/Export**
```python
def export_settings():
    return {
        'general': model_to_dict(get_general_settings()),
        'branding': model_to_dict(get_branding_settings()),
        # ...
    }
```

4. **Settings Templates**
```python
class SettingsTemplate(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    template_data = models.JSONField()
```

5. **Audit Logging**
```python
@receiver(post_save, sender=GeneralSettings)
def log_settings_change(sender, instance, **kwargs):
    SettingsAuditLog.objects.create(
        model=sender.__name__,
        instance_id=instance.id,
        action='update'
    )
```

## Best Practices

1. **Always use helper functions** to retrieve settings
2. **Cache settings** in production for performance
3. **Validate input** before saving sensitive data (API keys)
4. **Use environment variables** for truly sensitive data
5. **Version control** settings changes for audit trail
6. **Test settings** in staging before production
7. **Document** custom settings additions

## Migration Strategy

```bash
# Create migrations
python manage.py makemigrations store_settings

# Apply to all tenants
python manage.py migrate_schemas

# Initialize default settings for existing tenants
python manage.py shell
>>> from store_settings.utils import get_all_settings
>>> settings = get_all_settings()  # Auto-creates defaults
```

## Security Considerations

1. **Encrypt sensitive data** (API keys, secrets)
2. **Restrict admin access** to settings
3. **Log all changes** for audit trail
4. **Validate domains** before saving
5. **Sanitize HTML** in policy content
6. **Rate limit** settings API endpoints

## Integration with Dashboard

Settings should be accessible via dashboard at:
```
/dashboard/<prefix>/settings/general/
/dashboard/<prefix>/settings/branding/
/dashboard/<prefix>/settings/payment/
...
```

Each settings page should:
- Display current values
- Allow inline editing
- Show save confirmation
- Validate before saving
- Log changes
