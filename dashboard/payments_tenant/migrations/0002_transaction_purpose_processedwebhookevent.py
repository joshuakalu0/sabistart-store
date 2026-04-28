"""
Migration: Add purpose field to Transaction and create ProcessedWebhookEvent.

Changes
-------
Transaction.purpose
    New CharField(max_length=50, blank=True, db_index=True) that records the
    business context for a payment (e.g. "addon_purchase", "storefront_order",
    "subscription").  Blank by default for backward-compatibility.

ProcessedWebhookEvent
    New append-only table used as an idempotency guard for incoming webhook
    events.  A unique constraint on (gateway_provider, gateway_event_id)
    ensures each gateway event is processed exactly once, even under concurrent
    webhook delivery.
"""

import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments_tenant", "0001_initial"),
    ]

    operations = [
        # ── 1. Add Transaction.purpose ──────────────────────────────────────
        migrations.AddField(
            model_name="transaction",
            name="purpose",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=50,
                verbose_name="Purpose",
                help_text=(
                    "Business context for this payment, "
                    "e.g. addon_purchase, storefront_order, subscription."
                ),
                default="",
            ),
            preserve_default=False,
        ),

        # ── 2. ProcessedWebhookEvent ─────────────────────────────────────────
        migrations.CreateModel(
            name="ProcessedWebhookEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "gateway_provider",
                    models.CharField(
                        max_length=50,
                        verbose_name="Gateway Provider",
                        db_index=True,
                    ),
                ),
                (
                    "gateway_event_id",
                    models.CharField(
                        max_length=500,
                        verbose_name="Gateway Event ID",
                        db_index=True,
                        help_text=(
                            "The unique event identifier supplied by the gateway, "
                            "e.g. Paystack event ID."
                        ),
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Event Type",
                    ),
                ),
                (
                    "order_number",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=100,
                        verbose_name="Order / Purchase Reference",
                    ),
                ),
                (
                    "action_taken",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Action Taken",
                    ),
                ),
                (
                    "raw_payload",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="Raw Payload",
                    ),
                ),
                (
                    "processing_ms",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Processing Time (ms)",
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="webhook_events",
                        to="payments_tenant.transaction",
                    ),
                ),
            ],
            options={
                "verbose_name": "Processed Webhook Event",
                "verbose_name_plural": "Processed Webhook Events",
                "ordering": ["-created_at"],
            },
        ),
        # ── Core idempotency unique constraint ──
        migrations.AlterUniqueTogether(
            name="processedwebhookevent",
            unique_together={("gateway_provider", "gateway_event_id")},
        ),
        # ── Indexes ──
        migrations.AddIndex(
            model_name="processedwebhookevent",
            index=models.Index(
                fields=["gateway_provider", "gateway_event_id"],
                name="pwhe_provider_event_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="processedwebhookevent",
            index=models.Index(
                fields=["gateway_provider", "-created_at"],
                name="pwhe_provider_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="processedwebhookevent",
            index=models.Index(
                fields=["order_number"],
                name="pwhe_order_number_idx",
            ),
        ),
    ]
