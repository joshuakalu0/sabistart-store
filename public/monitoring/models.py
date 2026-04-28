from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class VisitorSession(models.Model):
    class Source(models.TextChoices):
        STOREFRONT = "storefront", "Storefront"
        DASHBOARD = "dashboard", "Dashboard"
        PLATFORM = "platform", "Platform"
        UNKNOWN = "unknown", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_key = models.CharField(max_length=64, db_index=True)
    schema_name = models.CharField(max_length=63, db_index=True, default="public")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.UNKNOWN, db_index=True)
    user_identifier = models.CharField(max_length=128, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    referrer = models.URLField(blank=True)
    landing_path = models.CharField(max_length=500, blank=True)
    last_path = models.CharField(max_length=500, blank=True)
    is_bot = models.BooleanField(default=False)
    visit_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["schema_name", "source", "last_seen_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.schema_name}:{self.source}:{self.session_key}"


class PageVisit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visitor_session = models.ForeignKey(
        VisitorSession,
        on_delete=models.CASCADE,
        related_name="page_visits",
    )
    schema_name = models.CharField(max_length=63, db_index=True, default="public")
    source = models.CharField(max_length=20, choices=VisitorSession.Source.choices, default=VisitorSession.Source.UNKNOWN, db_index=True)
    path = models.CharField(max_length=500, db_index=True)
    full_url = models.URLField(blank=True)
    route_name = models.CharField(max_length=255, blank=True, db_index=True)
    method = models.CharField(max_length=10, default="GET")
    referrer = models.URLField(blank=True)
    status_code = models.PositiveSmallIntegerField(default=200, db_index=True)
    server_duration_ms = models.PositiveIntegerField(default=0)
    client_duration_ms = models.PositiveIntegerField(default=0)
    engaged_seconds = models.PositiveIntegerField(default=0)
    page_title = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["schema_name", "source", "created_at"]),
            models.Index(fields=["path", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.source}:{self.path} ({self.status_code})"
