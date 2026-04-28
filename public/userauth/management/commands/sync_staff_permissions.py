from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from public.userauth.models import Permission, Role, RolePermission
from public.userauth.permission_registry import (
    ALL_PERMISSION_CODENAMES,
    BUILT_IN_ROLE_DEFINITIONS,
    PERMISSION_DEFINITIONS,
)


@dataclass
class SyncSummary:
    created_permissions: int = 0
    updated_permissions: int = 0
    deactivated_permissions: int = 0
    created_roles: int = 0
    updated_roles: int = 0
    created_role_permissions: int = 0
    deleted_role_permissions: int = 0


class Command(BaseCommand):
    help = "Create and sync tenant staff permissions and built-in roles across tenant schemas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            action="append",
            dest="schemas",
            help="Limit the sync to one or more tenant schemas. Defaults to all tenant schemas.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the sync without writing changes.",
        )

    def handle(self, *args, **options):
        schemas = options["schemas"] or self._all_tenant_schemas()
        dry_run = options["dry_run"]

        if not schemas:
            raise CommandError("No tenant schemas were found to sync.")

        for schema_name in schemas:
            with schema_context(schema_name):
                summary = self._sync_schema(schema_name=schema_name, dry_run=dry_run)
            mode = "DRY RUN" if dry_run else "SYNCED"
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{mode}] {schema_name}: "
                    f"permissions +{summary.created_permissions}/{summary.updated_permissions} updated, "
                    f"{summary.deactivated_permissions} stale inactive, "
                    f"roles +{summary.created_roles}/{summary.updated_roles} updated, "
                    f"role grants +{summary.created_role_permissions}/-{summary.deleted_role_permissions}"
                )
            )

    def _all_tenant_schemas(self) -> list[str]:
        TenantModel = get_tenant_model()
        public_schema = get_public_schema_name()
        return list(
            TenantModel.objects.exclude(schema_name=public_schema)
            .values_list("schema_name", flat=True)
            .order_by("schema_name")
        )

    def _sync_schema(self, *, schema_name: str, dry_run: bool) -> SyncSummary:
        summary = SyncSummary()
        registry_map = {definition.codename: definition for definition in PERMISSION_DEFINITIONS}
        active_codenames = set(registry_map)

        existing_permissions = {
            permission.codename: permission
            for permission in Permission.objects.all()
        }

        for definition in PERMISSION_DEFINITIONS:
            permission = existing_permissions.get(definition.codename)
            if permission is None:
                summary.created_permissions += 1
                if not dry_run:
                    Permission.objects.create(
                        name=definition.name,
                        codename=definition.codename,
                        description=definition.description,
                        category=definition.category,
                        is_system=True,
                        is_active=True,
                    )
                continue

            changed_fields = []
            if permission.name != definition.name:
                permission.name = definition.name
                changed_fields.append("name")
            if permission.description != definition.description:
                permission.description = definition.description
                changed_fields.append("description")
            if permission.category != definition.category:
                permission.category = definition.category
                changed_fields.append("category")
            if not permission.is_system:
                permission.is_system = True
                changed_fields.append("is_system")
            if not permission.is_active:
                permission.is_active = True
                changed_fields.append("is_active")

            if changed_fields:
                summary.updated_permissions += 1
                if not dry_run:
                    permission.save(update_fields=changed_fields + ["updated_at"])

        stale_permissions = Permission.objects.filter(is_system=True).exclude(codename__in=active_codenames)
        summary.deactivated_permissions = stale_permissions.exclude(is_active=False).count()
        if not dry_run and summary.deactivated_permissions:
            stale_permissions.update(is_active=False)

        permission_id_map = {
            codename: permission_id
            for codename, permission_id in Permission.objects.filter(codename__in=ALL_PERMISSION_CODENAMES).values_list("codename", "id")
        }

        for definition in BUILT_IN_ROLE_DEFINITIONS:
            role = Role.objects.filter(slug=definition.slug).first()
            created = role is None
            if created:
                summary.created_roles += 1
                if dry_run:
                    desired_codenames = (
                        ALL_PERMISSION_CODENAMES
                        if definition.permission_codenames == "ALL"
                        else tuple(definition.permission_codenames)
                    )
                    summary.created_role_permissions += len(desired_codenames)
                    continue

                role = Role.objects.create(
                    slug=definition.slug,
                    name=definition.name,
                    description=definition.description,
                    is_system=True,
                    is_active=True,
                    system_slug=definition.slug,
                    role_type="system",
                    color=definition.color,
                    sort_order=definition.sort_order,
                )

            changed_fields = []
            if role.name != definition.name:
                role.name = definition.name
                changed_fields.append("name")
            if role.description != definition.description:
                role.description = definition.description
                changed_fields.append("description")
            if role.system_slug != definition.slug:
                role.system_slug = definition.slug
                changed_fields.append("system_slug")
            if role.role_type != "system":
                role.role_type = "system"
                changed_fields.append("role_type")
            if role.color != definition.color:
                role.color = definition.color
                changed_fields.append("color")
            if role.sort_order != definition.sort_order:
                role.sort_order = definition.sort_order
                changed_fields.append("sort_order")
            if not role.is_system:
                role.is_system = True
                changed_fields.append("is_system")
            if not role.is_active:
                role.is_active = True
                changed_fields.append("is_active")

            if changed_fields:
                summary.updated_roles += 1
                if not dry_run:
                    role.save(update_fields=changed_fields + ["updated_at"])

            desired_codenames = (
                ALL_PERMISSION_CODENAMES
                if definition.permission_codenames == "ALL"
                else tuple(definition.permission_codenames)
            )
            desired_permission_ids = {
                permission_id_map[codename]
                for codename in desired_codenames
                if codename in permission_id_map
            }
            current_permission_ids = set(
                role.role_permissions.values_list("permission_id", flat=True)
            )
            missing_ids = desired_permission_ids - current_permission_ids
            stale_ids = current_permission_ids - desired_permission_ids

            summary.created_role_permissions += len(missing_ids)
            summary.deleted_role_permissions += len(stale_ids)

            if not dry_run and stale_ids:
                RolePermission.objects.filter(role=role, permission_id__in=stale_ids).delete()

            if not dry_run:
                for permission_id in missing_ids:
                    RolePermission.objects.get_or_create(role=role, permission_id=permission_id)

                target_permission_count = len(desired_permission_ids)
                if role._permission_count != target_permission_count:
                    role._permission_count = target_permission_count
                    role.save(update_fields=["_permission_count", "updated_at"])

        return summary
