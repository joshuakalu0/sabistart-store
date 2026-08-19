#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

from sabistart.bootstrap import bootstrap_paths
from sabistart.env import ensure_project_root_on_path, load_environment


def main():
    """Run administrative tasks."""
    bootstrap_paths(os.path.dirname(os.path.abspath(__file__)))
    ensure_project_root_on_path()
    load_environment()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabistart.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
