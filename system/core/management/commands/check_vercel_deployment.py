import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _requirements_declares(*package_prefixes: str) -> bool:
    requirements_path = Path(settings.BASE_DIR / "requirements.txt")
    if not requirements_path.exists():
        return False

    declared = {
        line.strip().lower()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return all(
        any(line.startswith(prefix.lower()) for line in declared)
        for prefix in package_prefixes
    )


class Command(BaseCommand):
    help = "Validate that the project is configured safely for Vercel deployment."

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

        storage_backend = settings.STORAGES["default"]["BACKEND"]

        checks.append(("debug_disabled", not settings.DEBUG, "DEBUG must be False in production."))
        checks.append(("secret_key", settings.SECRET_KEY and "django-insecure" not in settings.SECRET_KEY, "Set a real DJANGO_SECRET_KEY."))
        checks.append(("allowed_hosts", settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS != ["*"], "Set DJANGO_ALLOWED_HOSTS to your real domains."))
        checks.append(("csrf_trusted_origins", bool(settings.CSRF_TRUSTED_ORIGINS), "Set DJANGO_CSRF_TRUSTED_ORIGINS for your HTTPS domains."))
        checks.append(("platform_cname", settings.PLATFORM_CNAME not in {"", "localhost", "127.0.0.1"}, "Set PLATFORM_CNAME to the real platform hostname."))
        checks.append(("postgres_backend", settings.DATABASES["default"]["ENGINE"] == "django_tenants.postgresql_backend", "The project must use django_tenants.postgresql_backend."))
        checks.append(("static_root", bool(settings.STATIC_ROOT), "STATIC_ROOT must be configured."))
        checks.append(("media_url", bool(settings.MEDIA_URL), "MEDIA_URL must be configured."))
        checks.append(("vercel_config", Path(settings.BASE_DIR / "vercel.json").exists(), "vercel.json must exist at the app root."))
        checks.append(("api_entrypoint", Path(settings.BASE_DIR / "api" / "index.py").exists(), "api/index.py must exist for the Vercel Python runtime."))
        checks.append(("build_script", Path(settings.BASE_DIR / "deployment" / "vercel" / "build.sh").exists(), "deployment/vercel/build.sh must exist."))
        checks.append(("blob_storage", storage_backend == "sabistart_store.storage_backends.VercelBlobStorage", "Use sabistart_store.storage_backends.VercelBlobStorage for persistent media on Vercel."))
        checks.append(("python_version_pin", Path(settings.BASE_DIR / ".python-version").exists(), ".python-version must be committed so Vercel uses the intended Python runtime."))
        checks.append(("requirements_vercel_sdk", _requirements_declares("vercel"), "requirements.txt must declare the Python `vercel` package for Blob storage support."))
        checks.append(("requirements_requests", _requirements_declares("requests"), "requirements.txt must declare `requests` for the registrar integration layer."))
        checks.append(("requirements_dnspython", _requirements_declares("dnspython"), "requirements.txt must declare `dnspython` for DNS verification tasks."))

        for check_key, is_ok, message in checks:
            if is_ok:
                self.stdout.write(self.style.SUCCESS(f"[ok] {check_key}"))
            else:
                formatted = f"[warn] {check_key}: {message}"
                warnings.append(formatted)
                self.stdout.write(self.style.WARNING(formatted))

        if storage_backend == "sabistart_store.storage_backends.VercelBlobStorage" and not os.getenv("BLOB_READ_WRITE_TOKEN"):
            warning = "[warn] blob_token: BLOB_READ_WRITE_TOKEN is required for Vercel Blob media storage."
            warnings.append(warning)
            self.stdout.write(self.style.WARNING(warning))

        pooled_database_url = os.getenv("DATABASE_URL", "")
        if (
            os.getenv("VERCEL_RUN_MIGRATIONS", "0") == "1"
            and "-pooler." in pooled_database_url
            and not (os.getenv("DATABASE_URL_UNPOOLED") or os.getenv("DATABASE_URL_DIRECT"))
        ):
            warning = "[warn] migrations_connection: VERCEL_RUN_MIGRATIONS=1 with a Neon pooled DATABASE_URL requires DATABASE_URL_UNPOOLED or DATABASE_URL_DIRECT."
            warnings.append(warning)
            self.stdout.write(self.style.WARNING(warning))

        if getattr(settings, "DOMAIN_SIMULATE_INFRA", False):
            warning = "[warn] domain_simulation: DOMAIN_SIMULATE_INFRA is enabled. Disable it in production."
            warnings.append(warning)
            self.stdout.write(self.style.WARNING(warning))

        if strict and warnings:
            raise CommandError("Vercel deployment readiness check failed.")

        if warnings:
            self.stdout.write(self.style.WARNING("Deployment checks completed with warnings."))
        else:
            self.stdout.write(self.style.SUCCESS("Vercel deployment checks passed."))
