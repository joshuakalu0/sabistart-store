"""
Migration: Add POSCart and POSCartItem models.

POSCart  – one OPEN cart per cashier × store; captures a server-side
           cart that persists between product selection and checkout.
POSCartItem – a single line in a cart with a denormalised price snapshot
              so that subsequent price changes cannot affect a pending cart.

Note on the `session` field
---------------------------
POSSession does not yet have its own migration in this app, so we store
the session reference as a nullable UUID rather than a DB-level FK.
The application layer can still look up the related POSSession with
``POSSession.objects.filter(id=cart.session_id)`` when needed.
The FK relationship declared on the model is for convenience only; the
DB constraint will be added in a future migration once POSSession is tracked.
"""

import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0004_posproduct_image"),
        ("userauth", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="POSCart",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False
                    ),
                ),
                (
                    # Soft reference to POSSession – stored as UUID, no DB FK
                    # (POSSession does not yet have its own migration).
                    "session_id",
                    models.UUIDField(
                        blank=True,
                        null=True,
                        verbose_name="Session ID",
                        help_text="UUID of the related POSSession (no DB-level FK yet).",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("completed", "Completed"),
                            ("voided", "Voided"),
                        ],
                        db_index=True,
                        default="open",
                        max_length=12,
                    ),
                ),
                (
                    "completed_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "voided_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "cashier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pos_carts",
                        to="userauth.tenantuser",
                    ),
                ),
                (
                    "store",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pos_carts",
                        to="pos.store",
                    ),
                ),
                (
                    "transaction",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_cart",
                        to="pos.postransaction",
                    ),
                ),
            ],
            options={
                "verbose_name": "POS Cart",
                "verbose_name_plural": "POS Carts",
                "db_table": "pos_cart",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="poscart",
            index=models.Index(
                fields=["cashier", "store", "status"],
                name="pos_cart_cashier_store_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="poscart",
            index=models.Index(
                fields=["store", "status"],
                name="pos_cart_store_status_idx",
            ),
        ),
        migrations.CreateModel(
            name="POSCartItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False
                    ),
                ),
                (
                    "product_name",
                    models.CharField(max_length=255, verbose_name="Product Name"),
                ),
                (
                    "product_sku",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="SKU"
                    ),
                ),
                (
                    "unit_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        verbose_name="Unit Price (snapshot)",
                    ),
                ),
                (
                    "quantity",
                    models.PositiveIntegerField(
                        default=1, verbose_name="Quantity"
                    ),
                ),
                (
                    "line_total",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=14,
                        verbose_name="Line Total",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "cart",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="pos.poscart",
                    ),
                ),
                (
                    "catalog_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cart_items",
                        to="pos.poscatalogitem",
                    ),
                ),
                (
                    "store_inventory",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cart_items",
                        to="pos.storeinventory",
                    ),
                ),
            ],
            options={
                "verbose_name": "POS Cart Item",
                "verbose_name_plural": "POS Cart Items",
                "db_table": "pos_cart_item",
                "ordering": ["created_at"],
            },
        ),
    ]
