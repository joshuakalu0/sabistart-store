from __future__ import annotations

from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name

from system.account.models import PlatformUser
from system.core.models import Domain, Shop


def _normalize_hostname(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").strip().lower()
    return hostname


class Command(BaseCommand):
    help = "Create or update the public-schema domain for a Vercel deployment host."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hostname",
            default="",
            help="Hostname to register for the public schema. Defaults to PUBLIC_VERCEL_URL or VERCEL_URL.",
        )
        parser.add_argument(
            "--create-public-tenant",
            action="store_true",
            help="Create the public Shop row if it does not already exist.",
        )
        parser.add_argument(
            "--owner-email",
            default="",
            help="Owner email to use if the public Shop row must be created.",
        )
        parser.add_argument(
            "--name",
            default="Public Platform",
            help="Display name to use if the public Shop row must be created.",
        )
        parser.add_argument(
            "--make-primary",
            action="store_true",
            help="Mark this domain as the primary domain for the public schema.",
        )
        parser.add_argument(
            "--reassign",
            action="store_true",
            help="Allow reassigning an existing domain row from another tenant to the public schema.",
        )

    def handle(self, *args, **options):
        hostname = _normalize_hostname(
            options["hostname"]
            or self._env("PUBLIC_VERCEL_URL")
            or self._env("VERCEL_URL")
        )
        if not hostname:
            raise CommandError(
                "No Vercel hostname was provided. Pass --hostname or set PUBLIC_VERCEL_URL / VERCEL_URL."
            )

        public_schema = get_public_schema_name()
        public_shop = Shop.objects.filter(schema_name=public_schema).first()

        if public_shop is None:
            if not options["create_public_tenant"]:
                raise CommandError(
                    "The public Shop row does not exist. Re-run with --create-public-tenant "
                    "after ensuring a PlatformUser is available to own it."
                )
            public_shop = self._create_public_shop(
                schema_name=public_schema,
                owner_email=options["owner_email"] or self._env("PUBLIC_TENANT_OWNER_EMAIL"),
                name=options["name"] or self._env("PUBLIC_TENANT_NAME") or "Public Platform",
            )
            self.stdout.write(self.style.SUCCESS(f"[created] public tenant `{public_shop.schema_name}`"))

        existing = Domain.objects.filter(domain__iexact=hostname).select_related("tenant").first()
        make_primary = bool(options["make_primary"])

        if existing and existing.tenant_id != public_shop.id:
            if not options["reassign"]:
                raise CommandError(
                    f"The domain `{hostname}` is already attached to tenant `{existing.tenant.schema_name}`. "
                    "Re-run with --reassign if you want to move it to the public schema."
                )
            existing.tenant = public_shop
            existing.is_primary = make_primary or existing.is_primary
            existing.save(update_fields=["tenant", "is_primary"])
            domain = existing
            created = False
        else:
            domain, created = Domain.objects.get_or_create(
                domain=hostname,
                defaults={
                    "tenant": public_shop,
                    "is_primary": make_primary or not Domain.objects.filter(tenant=public_shop).exists(),
                },
            )
            if not created:
                updates = []
                if domain.tenant_id != public_shop.id:
                    domain.tenant = public_shop
                    updates.append("tenant")
                if make_primary and not domain.is_primary:
                    domain.is_primary = True
                    updates.append("is_primary")
                if updates:
                    domain.save(update_fields=updates)

        if domain.is_primary:
            Domain.objects.filter(tenant=public_shop, is_primary=True).exclude(pk=domain.pk).update(is_primary=False)

        status = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"[{status}] public domain `{domain.domain}` -> `{public_shop.schema_name}`"))

    def _create_public_shop(self, *, schema_name: str, owner_email: str, name: str) -> Shop:
        owner = None
        if owner_email:
            owner = PlatformUser.objects.filter(email__iexact=owner_email).first()
            if owner is None:
                raise CommandError(
                    f"No PlatformUser found for `{owner_email}`. "
                    "Create the user first or use a valid --owner-email / PUBLIC_TENANT_OWNER_EMAIL."
                )

        if owner is None:
            owner = PlatformUser.objects.filter(is_superuser=True).order_by("id").first()

        if owner is None:
            owner = PlatformUser.objects.order_by("id").first()

        if owner is None:
            raise CommandError(
                "Cannot create the public Shop row because no PlatformUser exists. "
                "Create an admin user first, then re-run this command."
            )

        public_shop = Shop(
            owner=owner,
            name=name,
            schema_name=schema_name,
        )
        public_shop.auto_create_schema = False
        public_shop.save()
        return public_shop

    @staticmethod
    def _env(name: str) -> str:
        import os

        return os.getenv(name, "")
