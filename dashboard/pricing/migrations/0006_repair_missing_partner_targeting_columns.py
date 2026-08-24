from django.db import migrations


FIELD_REPAIRS = {
    "AutomaticDiscount": (
        "attributed_partner",
        "eligible_cities",
        "eligible_countries",
        "eligible_states",
        "total_stack_cap_amount",
    ),
    "DiscountCode": (
        "attributed_partner",
        "eligible_cities",
        "eligible_countries",
        "eligible_states",
        "total_stack_cap_amount",
    ),
}


def repair_missing_columns(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names(cursor))

        for model_name, field_names in FIELD_REPAIRS.items():
            model = apps.get_model("pricing", model_name)
            table_name = model._meta.db_table
            if table_name not in existing_tables:
                continue

            existing_columns = {
                column.name
                for column in connection.introspection.get_table_description(cursor, table_name)
            }

            for field_name in field_names:
                field = model._meta.get_field(field_name)
                if field.column in existing_columns:
                    continue
                schema_editor.add_field(model, field)
                existing_columns.add(field.column)


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0005_automaticdiscount_attributed_partner_and_more"),
    ]

    operations = [
        migrations.RunPython(repair_missing_columns, migrations.RunPython.noop),
    ]
