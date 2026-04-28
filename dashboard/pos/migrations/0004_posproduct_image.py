from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0003_alter_storeinventory_unique_together_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="posproduct",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="pos/products/%Y/%m/"),
        ),
    ]
