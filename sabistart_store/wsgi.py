"""
WSGI config for sabistart_store project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from django.core.wsgi import get_wsgi_application

from sabistart_store.env import load_environment

load_environment()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabistart_store.settings')

application = get_wsgi_application()
