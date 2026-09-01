"""
Repair migration: ensure pos_catalog_items table exists.

Background
----------
Migration pos.0002 creates the POSCatalogItem model (table: pos_catalog_items)
and AddField operations that FK-link several models to it.  If the tenant schema
was bootstrapped while a prior Postgres transaction was aborted, django_migrations
may show 0002 as "applied" even though the DDL never committed.

This repair migration (inserted between 0004 and 0005) detects that situation
and re-creates the missing table + related FK columns from scratch so that
pos.0005 (which creates pos_cart_item with a FK to pos_catalog_items) can run
without raising "relation does not exist".
"""

import uuid
import django.db.models.deletion
from django.db import migrations, models


def _col_exists(cursor, table, column):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = %s
          AND column_name  = %s
        """,
        [table, column],
    )
    return cursor.fetchone() is not None


def _table_exists(cursor, table):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name   = %s
        """,
        [table],
    )
    return cursor.fetchone() is not None


def repair_pos_catalog_items(apps, schema_editor):
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        if not _table_exists(cursor, "pos_catalog_items"):
            # Re-create pos_catalog_items from scratch
            cursor.execute(
                """
                CREATE TABLE pos_catalog_items (
                    id              uuid        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                    created_at      timestamptz NOT NULL DEFAULT now(),
                    updated_at      timestamptz NOT NULL DEFAULT now(),
                    deleted_at      timestamptz,
                    is_deleted      boolean     NOT NULL DEFAULT false,
                    label_override  varchar(255) NOT NULL DEFAULT '',
                    barcode_override varchar(100) NOT NULL DEFAULT '',
                    quick_add_code  varchar(50)  NOT NULL DEFAULT '',
                    is_active       boolean      NOT NULL DEFAULT true,
                    allow_open_quantity boolean  NOT NULL DEFAULT false,
                    notes           text         NOT NULL DEFAULT '',
                    product_id      uuid         NOT NULL,
                    variant_id      uuid,
                    created_by_id   uuid,
                    updated_by_id   uuid,
                    deleted_by_id   uuid
                );
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS pos_catalog_items_product_id_variant_id_key
                    ON pos_catalog_items (product_id, variant_id);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS pos_catalog_items_barcode_override
                    ON pos_catalog_items (barcode_override);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS pos_catalog_items_quick_add_code
                    ON pos_catalog_items (quick_add_code);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS pos_catalog_items_is_active
                    ON pos_catalog_items (is_active);
                """
            )

        # Ensure FK columns exist on dependent tables
        # storeinventory.catalog_item_id
        if _table_exists(cursor, "pos_store_inventory"):
            if not _col_exists(cursor, "pos_store_inventory", "catalog_item_id"):
                cursor.execute(
                    """
                    ALTER TABLE pos_store_inventory
                    ADD COLUMN catalog_item_id uuid REFERENCES pos_catalog_items(id)
                        ON DELETE CASCADE;
                    """
                )

        # pos_transaction_items.catalog_item_id
        if _table_exists(cursor, "pos_transaction_items"):
            if not _col_exists(cursor, "pos_transaction_items", "catalog_item_id"):
                cursor.execute(
                    """
                    ALTER TABLE pos_transaction_items
                    ADD COLUMN catalog_item_id uuid REFERENCES pos_catalog_items(id)
                        ON DELETE SET NULL;
                    """
                )


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0004_posproduct_image"),
    ]

    operations = [
        migrations.RunPython(repair_pos_catalog_items, migrations.RunPython.noop),
    ]
