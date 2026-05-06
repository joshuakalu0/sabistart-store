import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sabistart_store.settings")

from sabistart_store.wsgi import application

app = application
