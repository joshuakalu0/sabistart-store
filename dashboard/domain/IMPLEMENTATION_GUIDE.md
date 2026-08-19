# Custom Domain Management System - Implementation Guide

## ✅ Phase 1 - COMPLETE
- Models (12 models) ✓
- Admin ✓
- Signals ✓
- Middleware ✓

## ✅ Phase 2 - IN PROGRESS
- Forms.py ✓ CREATED

## 📋 REMAINING IMPLEMENTATION TASKS

### PHASE 2 - Views & URLs (PRIORITY 1)

Create `dashboard/domain/views.py`:

```python
# Key imports needed:
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.conf import settings
from dashboard.domain.models import *
from dashboard.domain.forms import AddDomainForm, DomainSettingsForm
from dashboard.domain.tasks import verify_domain_dns

# Views to implement:
1. domain_list(request, prefix) - Main dashboard
2. domain_add(request, prefix) - HTMX add domain
3. domain_delete(request, prefix, domain_id) - Soft delete
4. domain_detail(request, prefix, domain_id) - Full detail page
5. domain_set_primary(request, prefix, domain_id) - Set primary
6. domain_retrigger_verification(request, prefix, domain_id) - Manual verify
7. domain_status_partial(request, prefix, domain_id) - HTMX polling
8. acme_challenge(request, token) - Public SSL validation endpoint
```

Create `dashboard/domain/urls.py`:

```python
from django.urls import path
from dashboard.domain import views

app_name = 'domain'

urlpatterns = [
    path('', views.domain_list, name='list'),
    path('add/', views.domain_add, name='add'),
    path('<uuid:domain_id>/', views.domain_detail, name='detail'),
    path('<uuid:domain_id>/delete/', views.domain_delete, name='delete'),
    path('<uuid:domain_id>/set-primary/', views.domain_set_primary, name='set_primary'),
    path('<uuid:domain_id>/verify/', views.domain_retrigger_verification, name='verify'),
    path('<uuid:domain_id>/status/', views.domain_status_partial, name='status'),
]

# Add to root urls.py for ACME:
# path('.well-known/acme-challenge/<str:token>/', views.acme_challenge, name='acme_challenge'),
```

### PHASE 3 - Celery Tasks (PRIORITY 2)

Create `dashboard/domain/tasks.py`:

```python
from celery import shared_task
import dns.resolver
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def verify_domain_dns(self, domain_id):
    """
    Core DNS verification task.
    - Check A record matches SERVER_IP
    - Check TXT record matches verification_token
    - Use multiple resolvers (8.8.8.8, 1.1.1.1, 8.8.4.4)
    - Log to DomainVerificationAttempt
    """
    pass

@shared_task(bind=True, max_retries=3)
def provision_ssl_certificate(self, domain_id):
    """
    Provision SSL via Let's Encrypt ACME protocol.
    - Create SSLCertificate record
    - Log to SSLProvisioningLog
    - Call ssl.ACMEClient
    - Trigger generate_nginx_config on success
    """
    pass

@shared_task
def generate_nginx_config(domain_id):
    """
    Generate and apply Nginx config.
    - Render Jinja2 template
    - Write to /etc/nginx/sites-enabled/
    - Test with nginx -t
    - Reload nginx
    - Set domain status to ACTIVE
    """
    pass

@shared_task
def run_domain_health_check(domain_id):
    """
    Check DNS, SSL, HTTP 200 response.
    - Write DomainHealthCheck row
    - Send notification if 3 consecutive failures
    """
    pass

@shared_task
def renew_expiring_certificates():
    """
    Beat task - renew certs expiring within 30 days.
    """
    pass

@shared_task
def cleanup_expired_acme_challenges():
    """
    Beat task - delete expired ACMEChallenge rows.
    """
    pass

@shared_task
def poll_pending_domains():
    """
    Beat task - verify all pending/dns_checking domains.
    Exponential backoff: 60s first hour, 10min hours 2-24, hourly after.
    """
    pass
```

Create `dashboard/domain/celery_schedule.py`:

```python
from celery.schedules import crontab

DOMAIN_BEAT_SCHEDULE = {
    'poll-pending-domains': {
        'task': 'dashboard.domain.tasks.poll_pending_domains',
        'schedule': 60.0,  # Every 60 seconds
    },
    'renew-expiring-certificates': {
        'task': 'dashboard.domain.tasks.renew_expiring_certificates',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'cleanup-expired-acme-challenges': {
        'task': 'dashboard.domain.tasks.cleanup_expired_acme_challenges',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    'run-health-checks': {
        'task': 'dashboard.domain.tasks.run_all_health_checks',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
}
```

### PHASE 4 - SSL Automation (PRIORITY 3)

Create `dashboard/domain/ssl.py`:

```python
from acme import client, messages, challenges
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography import x509
import josepy as jose
import OpenSSL

class ACMEClient:
    """
    Wrapper for ACME protocol interaction with Let's Encrypt.
    """
    def __init__(self, domain):
        self.domain = domain
        self.directory_url = 'https://acme-v02.api.letsencrypt.org/directory'
        # Use staging for testing: https://acme-staging-v02.api.letsencrypt.org/directory
    
    def create_account(self):
        """Create or load ACME account."""
        pass
    
    def place_order(self):
        """Place certificate order."""
        pass
    
    def create_http01_challenge(self):
        """Create HTTP-01 challenge and store in ACMEChallenge table."""
        pass
    
    def poll_challenge(self):
        """Poll until Let's Encrypt validates challenge."""
        pass
    
    def download_certificate(self):
        """Download issued certificate."""
        pass
    
    def store_certificate(self, cert, key, chain):
        """Store cert files to /etc/ssl/sabistart/<domain>/"""
        pass

class SSLRenewal:
    """Handle SSL certificate renewal."""
    def renew(self, domain):
        """Renew certificate using existing ACME account."""
        pass

def verify_ssl_validity(domain):
    """
    Open socket to domain:443, retrieve cert, check expiry and hostname.
    Used by health check task.
    """
    pass
```

### PHASE 5 - Nginx Automation (PRIORITY 4)

Create `dashboard/domain/nginx.py`:

```python
from jinja2 import Environment, FileSystemLoader
import subprocess
import hashlib
import os

class NginxConfigGenerator:
    """Generate Nginx server block from template."""
    def __init__(self, custom_domain):
        self.domain = custom_domain
        self.template_path = os.path.join(
            os.path.dirname(__file__),
            'templates/nginx'
        )
    
    def render(self):
        """Render Jinja2 template with domain data."""
        env = Environment(loader=FileSystemLoader(self.template_path))
        template = env.get_template('vhost.conf.j2')
        
        context = {
            'domain': self.domain.domain,
            'ssl_cert_path': self.domain.ssl_cert_path,
            'ssl_key_path': self.domain.ssl_key_path,
            'upstream': 'unix:/run/gunicorn.sock',  # Adjust as needed
        }
        
        return template.render(context)

class NginxConfigWriter:
    """Write and apply Nginx config."""
    def __init__(self, custom_domain):
        self.domain = custom_domain
        self.config_dir = '/etc/nginx/sites-enabled'
    
    def write(self, config_content):
        """
        Write config, test, reload nginx.
        - Write to /etc/nginx/sites-enabled/<domain>.conf
        - Create NginxVhostConfig snapshot
        - Run nginx -t
        - If test passes: systemctl reload nginx
        - If test fails: rollback to previous config
        """
        pass
    
    def test_config(self):
        """Run nginx -t to validate config."""
        result = subprocess.run(
            ['sudo', 'nginx', '-t'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    
    def reload_nginx(self):
        """Reload nginx service."""
        subprocess.run(['sudo', 'systemctl', 'reload', 'nginx'])
    
    def rollback(self):
        """Restore previous config snapshot."""
        pass
```

Create `dashboard/domain/templates/nginx/vhost.conf.j2`:

```nginx
# Nginx vhost for {{ domain }}
# Generated automatically - do not edit manually

# HTTP -> HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name {{ domain }};
    
    # ACME challenge location
    location /.well-known/acme-challenge/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # Redirect all other traffic to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {{ domain }};
    
    # SSL Configuration
    ssl_certificate {{ ssl_cert_path }};
    ssl_certificate_key {{ ssl_key_path }};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Gzip Compression
    gzip on;
    gzip_vary on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    
    # Client upload size
    client_max_body_size 100M;
    
    # Proxy to Django/Gunicorn
    location / {
        proxy_pass http://{{ upstream }};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
    
    # Static files
    location /static/ {
        alias /var/www/sabistart/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    # Media files
    location /media/ {
        alias /var/www/sabistart/media/;
        expires 7d;
    }
}
```

### PHASE 6 - Templates (PRIORITY 5)

All templates go in `dashboard/domain/templates/domains/`

**Key templates to create:**

1. `domain_list.html` - Main dashboard with domain cards
2. `domain_detail.html` - Full domain detail page
3. `partials/domain_card.html` - Individual domain card
4. `partials/domain_status_badge.html` - Status badge for HTMX polling
5. `partials/dns_instructions_table.html` - DNS setup instructions
6. `partials/add_domain_modal.html` - HTMX modal for adding domain

**Template structure pattern:**
```django
{% extends "dashboard/_partials/base.html" %}
{% block content %}
<div class="max-w-7xl mx-auto">
    <!-- Page header -->
    <div class="flex items-center justify-between mb-6">
        <div>
            <h1 class="text-2xl font-bold text-slate-900 dark:text-white">Custom Domains</h1>
            <p class="text-sm text-slate-600 dark:text-slate-400 mt-1">Connect your own domain to your store</p>
        </div>
        <button onclick="openAddDomainModal()" class="px-4 py-2 bg-primary text-white rounded-lg hover:bg-blue-600 transition-colors">
            <span class="material-icons-outlined text-sm mr-2">add</span>
            Add Domain
        </button>
    </div>
    
    <!-- Quota indicator -->
    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4 mb-6">
        <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-slate-700 dark:text-slate-300">Domain Usage</span>
            <span class="text-sm text-slate-600 dark:text-slate-400">{{ quota.domains_used }} of {{ quota.max_custom_domains }}</span>
        </div>
        <div class="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2">
            <div class="bg-primary h-2 rounded-full" style="width: {{ quota.domains_used|div:quota.max_custom_domains|mul:100 }}%"></div>
        </div>
    </div>
    
    <!-- Domain cards grid -->
    <div id="domain-list" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {% for domain in domains %}
            {% include 'domains/partials/domain_card.html' %}
        {% empty %}
            <!-- Empty state -->
            <div class="col-span-full">
                <div class="bg-white dark:bg-slate-800 rounded-xl border-2 border-dashed border-slate-300 dark:border-slate-600 p-12 text-center">
                    <span class="material-icons-outlined text-6xl text-slate-400 mb-4">language</span>
                    <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-2">No custom domains yet</h3>
                    <p class="text-slate-600 dark:text-slate-400 mb-6">Connect your own domain to give your store a professional look</p>
                    <button onclick="openAddDomainModal()" class="px-6 py-3 bg-primary text-white rounded-lg hover:bg-blue-600 transition-colors">
                        Add Your First Domain
                    </button>
                </div>
            </div>
        {% endfor %}
    </div>
</div>

<!-- HTMX polling for pending domains -->
<script>
    // Poll status every 15 seconds for non-final states
    document.addEventListener('DOMContentLoaded', function() {
        const pendingDomains = document.querySelectorAll('[data-domain-status="pending"], [data-domain-status="dns_checking"], [data-domain-status="ssl_pending"]');
        
        pendingDomains.forEach(card => {
            const domainId = card.dataset.domainId;
            setInterval(() => {
                fetch(`/domains/${domainId}/status/`)
                    .then(response => response.text())
                    .then(html => {
                        const statusContainer = card.querySelector('.domain-status');
                        if (statusContainer) {
                            statusContainer.innerHTML = html;
                        }
                    });
            }, 15000);
        });
    });
</script>
{% endblock %}
```

### PHASE 7 - Security & Notifications (PRIORITY 6)

Create `dashboard/domain/security.py`:

```python
def validate_domain_ownership(domain, tenant):
    """Verify TXT record contains THIS tenant's token."""
    pass

def check_domain_hijacking(domain):
    """Check if domain already exists for another tenant."""
    pass

class DomainQuotaEnforcer:
    """Mixin to check quota before domain add."""
    @staticmethod
    def check_quota(tenant):
        quota = tenant.domain_quota
        if not quota.has_capacity:
            return False, f"You've reached your limit of {quota.max_custom_domains} domains. Upgrade your plan to add more."
        return True, None
```

Create `dashboard/domain/notifications.py`:

```python
from django.core.mail import send_mail
from django.template.loader import render_to_string

def notify_domain_verified(domain):
    """Send email when domain is verified."""
    pass

def notify_ssl_active(domain):
    """Send email when SSL is live."""
    pass

def notify_ssl_expiring(domain, days_remaining):
    """Send email 30 and 7 days before expiry."""
    pass

def notify_verification_failed(domain, reason):
    """Send email if verification fails for 24+ hours."""
    pass

def notify_domain_health_failing(domain):
    """Send email if 3 consecutive health checks fail."""
    pass
```

Create `dashboard/domain/mixins.py`:

```python
from django.shortcuts import get_object_or_404
from django.http import Http404

class TenantDomainOwnershipMixin:
    """Ensure domain belongs to current tenant."""
    def dispatch(self, request, *args, **kwargs):
        domain_id = kwargs.get('domain_id')
        domain = get_object_or_404(CustomDomain, id=domain_id)
        if domain.tenant != request.tenant:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

class DomainQuotaMixin:
    """Check quota before domain add."""
    pass

class DomainFeatureRequiredMixin:
    """Check if tenant's plan includes custom domains."""
    pass
```

### FINAL WIRING

1. **Add to tenant URLs** (`dashboard/urls.py`):
```python
path('domains/', include('dashboard.domain.urls')),
```

2. **Add ACME challenge to root URLs**:
```python
path('.well-known/acme-challenge/<str:token>/', domain_views.acme_challenge, name='acme_challenge'),
```

3. **Add to Celery beat schedule** (`sabistart/celery.py`):
```python
from dashboard.domain.celery_schedule import DOMAIN_BEAT_SCHEDULE
app.conf.beat_schedule.update(DOMAIN_BEAT_SCHEDULE)
```

4. **Management commands**:
- `dashboard/domain/management/commands/verify_all_pending_domains.py`
- `dashboard/domain/management/commands/check_ssl_expiry.py`

5. **Sudoers entry** (add to `/etc/sudoers.d/django-nginx`):
```
www-data ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t
www-data ALL=(ALL) NOPASSWD: /bin/systemctl reload nginx
```

6. **Settings additions** (`settings.py`):
```python
SERVER_IP = '1.2.3.4'  # Your server's public IP
ACME_DIRECTORY_URL = 'https://acme-v02.api.letsencrypt.org/directory'
ACME_STAGING_URL = 'https://acme-staging-v02.api.letsencrypt.org/directory'
SSL_CERT_BASE_PATH = '/etc/ssl/sabistart'
NGINX_SITES_ENABLED = '/etc/nginx/sites-enabled'
```

## IMPLEMENTATION ORDER

1. ✅ Forms (DONE)
2. Views & URLs (Start here)
3. Basic templates (domain_list, domain_detail)
4. Celery tasks (verify_domain_dns first)
5. SSL automation
6. Nginx automation
7. Remaining templates & HTMX
8. Security & notifications
9. Management commands
10. Testing & deployment

## TESTING CHECKLIST

- [ ] Add domain with valid format
- [ ] Reject invalid domain formats
- [ ] Reject duplicate domains
- [ ] DNS verification with correct records
- [ ] DNS verification with wrong records
- [ ] SSL provisioning end-to-end
- [ ] Nginx config generation and reload
- [ ] Domain health checks
- [ ] SSL renewal 30 days before expiry
- [ ] Quota enforcement
- [ ] HTMX polling updates status
- [ ] Primary domain switching
- [ ] Domain removal
- [ ] ACME challenge serving
- [ ] Email notifications

## DEPLOYMENT NOTES

- Ensure Celery worker and beat are running
- Ensure Redis is running for cache
- Ensure Nginx has write permissions for config directory
- Test with Let's Encrypt staging first
- Monitor Celery logs for task failures
- Set up monitoring for SSL expiry
- Configure email backend for notifications
