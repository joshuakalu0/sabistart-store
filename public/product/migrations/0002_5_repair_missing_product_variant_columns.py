"""
Repair migration: ensure product_productvariant.product_id exists.

Background
----------
Migration product.0002 adds the `product` FK to ProductVariant.
If a tenant schema was initialized during a partial migration pass,
product_productvariant may exist without the product_id column.

This migration checks and adds the product_id column if missing.
"""

from django.db import migrations


def repair_product_variant_columns(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names(cursor))
        if "product_productvariant" in existing_tables:
            existing_columns = {
                col.name
                for col in connection.introspection.get_table_description(
                    cursor, "product_productvariant"
                )
            }
            if "product_id" not in existing_columns:
                cursor.execute("""
                    ALTER TABLE product_productvariant
                    ADD COLUMN product_id uuid REFERENCES product_product(id) ON DELETE CASCADE;
                """)


class Migration(migrations.Migration):

    dependencies = [
        ("product", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(repair_product_variant_columns, migrations.RunPython.noop),
    ]
