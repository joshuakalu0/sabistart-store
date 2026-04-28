from __future__ import annotations

from collections.abc import Callable

from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django_tenants.utils import schema_context


DB_ERRORS = (OperationalError, ProgrammingError)


def safe_platform_call(func: Callable[[], object], default):
    try:
        return func()
    except DB_ERRORS:
        return default() if callable(default) else default


def missing_shared_tables(*models) -> list[str]:
    try:
        schema_name = getattr(connection, "schema_name", "public")
        if schema_name != "public":
            with schema_context("public"):
                available_tables = set(connection.introspection.table_names())
        else:
            available_tables = set(connection.introspection.table_names())
    except DB_ERRORS:
        return [model._meta.db_table for model in models]
    return [model._meta.db_table for model in models if model._meta.db_table not in available_tables]


def setup_warning_for(label: str, *models) -> str:
    missing = missing_shared_tables(*models)
    if not missing:
        return ""
    preview = ", ".join(missing[:4])
    if len(missing) > 4:
        preview = f"{preview}, ..."
    return (
        f"{label} setup is incomplete. Run manage.py migrate_schemas --shared "
        f"to create the missing shared tables ({preview})."
    )
