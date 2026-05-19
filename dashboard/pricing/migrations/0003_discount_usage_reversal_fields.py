from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0002_initial"),
    ]

    operations = [
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
