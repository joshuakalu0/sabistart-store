from celery.schedules import crontab


DOMAIN_BEAT_SCHEDULE = {
    "poll-pending-domains": {
        "task": "dashboard.domain.tasks.poll_pending_domains",
        "schedule": 60.0,
    },
    "renew-expiring-certificates": {
        "task": "dashboard.domain.tasks.renew_expiring_certificates",
        "schedule": crontab(hour=2, minute=0),
    },
    "cleanup-expired-acme-challenges": {
        "task": "dashboard.domain.tasks.cleanup_expired_acme_challenges",
        "schedule": crontab(minute="*/30"),
    },
    "run-domain-health-checks": {
        "task": "dashboard.domain.tasks.run_all_health_checks",
        "schedule": crontab(minute="*/15"),
    },
}
