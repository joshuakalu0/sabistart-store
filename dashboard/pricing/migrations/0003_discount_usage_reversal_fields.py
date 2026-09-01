from django.db import migrations, models


def ensure_discount_usage_columns(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names(cursor))
        model = apps.get_model("pricing", "DiscountUsage")
        table_name = model._meta.db_table
        if table_name not in existing_tables:
            return

        existing_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }

        # Ensure discount_code_id exists
        if "discount_code_id" not in existing_columns:
            try:
                discount_code_field = model._meta.get_field("discount_code")
                schema_editor.add_field(model, discount_code_field)
                existing_columns.add("discount_code_id")
            except Exception:
                pass

        # Ensure customer_id exists
        if "customer_id" not in existing_columns:
            try:
                customer_field = model._meta.get_field("customer")
                schema_editor.add_field(model, customer_field)
                existing_columns.add("customer_id")
            except Exception:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(ensure_discount_usage_columns, migrations.RunPython.noop),
        migrations.AddField(
            model_name="discountusage",
            name="is_reversed",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "Marks redemptions that were later voided or cancelled so they are "
                    "excluded from live validation and analytics."
                ),
                verbose_name="Is Reversed",
            ),
        ),
        migrations.AddField(
            model_name="discountusage",
            name="reversed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Reversed At",
            ),
        ),
        migrations.AddField(
            model_name="discountusage",
            name="reversal_reason",
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name="Reversal Reason",
            ),
        ),
        migrations.AddIndex(
            model_name="discountusage",
            index=models.Index(
                fields=["discount_code", "is_reversed", "-used_at"],
                name="pricing_dis_discount_d1bda4_idx",
            ),
        ),
    ]

