import os
import sys
from pathlib import Path

RAW_BASE_DIR = Path(__file__).resolve().parent.parent
if str(RAW_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(RAW_BASE_DIR))

from sabistart_store.bootstrap import bootstrap_paths

BASE_DIR = bootstrap_paths(RAW_BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sabistart_store.settings")

from sabistart_store.wsgi import application

app = application
