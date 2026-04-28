# ─────────────────────────────────────────────────────────────────────────────
# Add these to your existing settings.py
# ─────────────────────────────────────────────────────────────────────────────

# ── Installed Apps ────────────────────────────────────────────────────────────
# Add 'domains' to your INSTALLED_APPS list:
#
# INSTALLED_APPS = [
#     'django_tenants',
#     'tenants',
#     'domains',        # ← add this
#     ...
# ]

# ── Middleware ────────────────────────────────────────────────────────────────
# Replace django_tenants' middleware with ours (must be FIRST):
#
# MIDDLEWARE = [
#     'domains.middleware.CustomDomainMiddleware',   # ← replaces TenantMainMiddleware
#     'django.middleware.security.SecurityMiddleware',
#     'django.contrib.sessions.middleware.SessionMiddleware',
#     'django.middleware.common.CommonMiddleware',
#     'django.middleware.csrf.CsrfViewMiddleware',
#     'django.contrib.auth.middleware.AuthenticationMiddleware',
#     'django.contrib.messages.middleware.MessageMiddleware',
#     'django.middleware.clickjacking.XFrameOptionsMiddleware',
# ]

# ── Custom Domain Settings ────────────────────────────────────────────────────

# Your server's public IPv4 address — this is what tenants point A records at
SERVER_IP = '123.45.67.89'

# The CNAME target for subdomain-based custom domains (www records etc.)
PLATFORM_CNAME = 'proxy.yourplatform.com'

# The suffix that identifies YOUR platform's native subdomains
# e.g. tenant.yourplatform.com — used to skip custom domain resolution
SUBDOMAIN_SUFFIX = '.yourplatform.com'

# How long to cache domain→tenant resolution in Redis (seconds)
# 300 = 5 minutes. Increase for performance, decrease for faster propagation.
DOMAIN_RESOLUTION_CACHE_TTL = 300

# ── Redis Cache (required) ────────────────────────────────────────────────────
# Install: pip install django-redis
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'RETRY_ON_TIMEOUT': True,
            'MAX_CONNECTIONS': 1000,
        },
        'KEY_PREFIX': 'sabistart',
    }
}

# ── Celery (required for background verification + SSL) ───────────────────────
# Install: pip install celery redis
CELERY_BROKER_URL         = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND     = 'redis://127.0.0.1:6379/0'
CELERY_ACCEPT_CONTENT     = ['json']
CELERY_TASK_SERIALIZER    = 'json'
CELERY_RESULT_SERIALIZER  = 'json'
CELERY_TIMEZONE           = 'Africa/Lagos'

# ── Logging (optional but recommended) ───────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'domains.middleware': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'domains.signals':    {'handlers': ['console'], 'level': 'INFO',  'propagate': False},
        'domains.tasks':      {'handlers': ['console'], 'level': 'INFO',  'propagate': False},
    },
}
