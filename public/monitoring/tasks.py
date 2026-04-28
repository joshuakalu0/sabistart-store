from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from public.monitoring.models import PageVisit, VisitorSession


logger = logging.getLogger(__name__)


def prune_stale_monitoring_data(*, days: int = 90) -> int:
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = PageVisit.objects.filter(created_at__lt=cutoff).delete()
    VisitorSession.objects.filter(last_seen_at__lt=cutoff).delete()
    logger.info("Pruned %s monitoring visits older than %s days", deleted, days)
    return deleted
