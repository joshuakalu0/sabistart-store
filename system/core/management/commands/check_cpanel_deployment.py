from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Validate that the project is configured safely for cPanel/Passenger deployment."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail on warnings that should be fixed before production deployment.",
        )

    def handle(self, *args, **options):
        strict = options["strict"]
        warnings = []
        checks = []

        checks.append(("debug_disabled", not settings.DEBUG, "DEBUG must be False in production."))
        checks.append(("secret_key", settings.SECRET_KEY and "django-insecure" not in settings.SECRET_KEY, "Set a real DJANGO_SECRET_KEY."))
        checks.append(("allowed_hosts", settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS != ["*"], "Set DJANGO_ALLOWED_HOSTS to your real domains."))
        checks.append(("csrf_trusted_origins", bool(settings.CSRF_TRUSTED_ORIGINS), "Set DJANGO_CSRF_TRUSTED_ORIGINS for your HTTPS domains."))
        checks.append(("postgres_backend", settings.DATABASES["default"]["ENGINE"] == "django_tenants.postgresql_backend", "The project must use django_tenants.postgresql_backend."))
        checks.append(("static_root", bool(settings.STATIC_ROOT), "STATIC_ROOT must be configured."))
        checks.append(("media_root", bool(settings.MEDIA_ROOT), "MEDIA_ROOT must be configured."))
        checks.append(("passenger_wsgi", Path(settings.BASE_DIR / "passenger_wsgi.py").exists(), "passenger_wsgi.py must exist at the app root."))

        for check_key, is_ok, message in checks:
            if is_ok:
                self.stdout.write(self.style.SUCCESS(f"[ok] {check_key}"))
            else:
                formatted = f"[warn] {check_key}: {message}"
                warnings.append(formatted)
                self.stdout.write(self.style.WARNING(formatted))

        if getattr(settings, "DOMAIN_SIMULATE_INFRA", False):
            warnings.append("[warn] domain_simulation: DOMAIN_SIMULATE_INFRA is enabled. Disable it in production.")
            self.stdout.write(self.style.WARNING(warnings[-1]))

        if strict and warnings:
            raise CommandError("cPanel deployment readiness check failed.")

        if warnings:
            self.stdout.write(self.style.WARNING("Deployment checks completed with warnings."))
        else:
            self.stdout.write(self.style.SUCCESS("cPanel deployment checks passed."))
