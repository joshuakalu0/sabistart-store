"""
ASGI config for sabistart project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import sys
from pathlib import Path

RAW_BASE_DIR = Path(__file__).resolve().parent.parent
if str(RAW_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(RAW_BASE_DIR))

from django.core.asgi import get_asgi_application

from sabistart.bootstrap import bootstrap_paths
from sabistart.env import load_environment

BASE_DIR = bootstrap_paths(RAW_BASE_DIR)
load_environment()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabistart.settings')

application = get_asgi_application()
