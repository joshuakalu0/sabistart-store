"""
manage.py process_pending_tenants
=================================
OS-isolated, cron-driven provisioning sweep for low-resource multi-tenant
hosts (1 vCPU / 1 GB RAM GCloud e2-micro class).

Why this exists
---------------
* The in-process chunked runner and the Worker Microservice both share
  memory with Gunicorn (or, in the case of the worker microservice, are
  still constrained by the same VM). On 1 GB hosts, running the migration
  DDL in a separate OS process is the only way to avoid OOM kills.
* Celery, Redis queue workers, and in-process threading have already
  been ruled out for this environment, so this command is the
  intentional backup path: it is invoked by plain OS ``cron`` (or by a
  developer running it manually on Windows).

What it does, per pending tenant
---------------------------------
Each cron tick applies EXACTLY ONE migration per tenant schema.
This prevents OOM, prevents stuck progress, and gives the UI live
incremental progress on every cron tick.

1. SELECTs the oldest Shop rows whose ``provisioning_status`` is
   ``PENDING`` / ``PROVISIONING`` / ``IN_PROGRESS`` / ``FAILED``
   (subject to the failure-cooldown gate).
2. Acquires the per-schema migration lock.
3. Flips ``provisioning_status`` to ``IN_PROGRESS``.
4. Pre-flight: repairs "lying" migration records (recorded as applied
   but the DDL table does not exist).
5. Runs exactly ONE pending migration by invoking
   ``run_tenant_chunked_migrations --schema=<name> --chunk-size=1
   --max-chunks=1`` as a subprocess.
6. Writes granular progress to ``Shop.provisioning_error`` so the UI
   polling endpoint can show live ``X/Y migrations applied`` even before
   the tenant schema's ``django_migrations`` table is readable.
7. If the subprocess indicates all done (exit code 2 = complete), calls
   ``_finalise_if_complete`` (entitlements, admin user, READY flip).
8. On any failure: flips the row to ``FAILED`` with captured output and
   sets the failure-cooldown so we don't busy-loop on a broken schema.
9. Releases the lock and moves to the next pending tenant.
10. Stops after ``--max-per-run`` tenants (default 1).

Exit codes from run_tenant_chunked_migrations subprocess
---------------------------------------------------------
0 = applied 1 migration, more remain
1 = migration failure
2 = all migrations already applied / nothing to do

Key properties
--------------
* ONE migration per cron tick. No concurrency. Deliberate.
* Each failed tenant is isolated.
* Idempotent: re-running on the same set just picks up where the last
  run stopped.
* No Celery, no threads, no Redis for DDL — pure cron + subprocess.

Example usage
-------------
    # Local dry-run (does not change anything; just prints what would
    # be processed). Safe to run on Windows.
    python manage.py process_pending_tenants --dry-run

    # Process up to 3 pending tenants per tick.
    python manage.py process_pending_tenants --max-per-run 3

    # Process a single specific schema by hand (debugging).
    python manage.py process_pending_tenants --schema onboard_ab12cd34

Cron entry (Linux VM)
---------------------
    */2 * * * * /home/sabistart/.venv/bin/python \\
        /home/sabistart/www/django/manage.py process_pending_tenants \\
        --max-per-run 1 \\
        >> /home/sabistart/logs/provision.log 2>&1
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


logger = logging.getLogger("sabistart.provisioning.cron")


# Statuses that mean "this tenant still needs work".
_PENDING_STATUSES = (
    "pending",
    "provisioning",
    "in_progress",
    "failed",
)

# Subprocess hard timeout for a single migration (generous).
DEFAULT_SUBPROCESS_TIMEOUT = 300  # 5 minutes per single migration


class Command(BaseCommand):
    help = (
        "Cron-driven, OS-isolated sweep that applies ONE migration per "
        "tenant schema per cron tick in a separate process, then "
        "finalises provisioning (entitlements, tenant admin user, READY "
        "status) once all migrations are applied. One tenant at a time. "
        "Safe to run on a 1 vCPU / 1 GB host."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            action="append",
            default=[],
            help=(
                "Process only these specific schema names (repeatable). "
                "If omitted, all tenants whose provisioning_status is "
                "pending/provisioning/in_progress/failed are considered, "
                "oldest first."
            ),
        )
        parser.add_argument(
            "--max-per-run",
            type=int,
            default=1,
            help=(
                "Maximum number of tenants to process in this invocation. "
                "Default 1 - one tenant per cron tick, on purpose, so the "
                "host can breathe."
            ),
        )
        parser.add_argument(
            "--subprocess-timeout",
            type=int,
            default=DEFAULT_SUBPROCESS_TIMEOUT,
            help=(
                "Hard wall-clock timeout (seconds) for the single-migration "
                "subprocess per tenant. Default 300 (5 min)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Print which tenants would be processed and the exact "
                "subprocess command that would run, but do not change "
                "any state."
            ),
        )
        parser.add_argument(
            "--skip-cooldown",
            action="store_true",
            help=(
                "Override the failure-cooldown gate so FAILED tenants "
                "are retried immediately."
            ),
        )

    # ------------------------------------------------------------------ #
    # Main entry point                                                    #
    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        from system.account.migration_runner import (
            acquire_migration_lock,
            clear_failure_cooldown,
            in_failure_cooldown,
            release_migration_lock,
        )
        from system.core.models import Shop

        subprocess_python = sys.executable

        # 1. Build the candidate queryset --------------------------------
        explicit_schemas: List[str] = [
            s.strip().lower() for s in options["schema"] if s and s.strip()
        ]
        if explicit_schemas:
            candidates = list(
                Shop.objects.filter(schema_name__in=explicit_schemas).order_by("created_on")
            )
        else:
            candidates = list(
                Shop.objects.filter(provisioning_status__in=_PENDING_STATUSES)
                .exclude(provisioning_status=Shop.ProvisioningStatus.READY)
                .order_by("created_on")
            )

        if not candidates:
            self.stdout.write(self.style.SUCCESS(
                "[CronProvision] No pending tenants. Exiting cleanly."
            ))
            return

        # 2. Apply cooldowns / selection logic ---------------------------
        max_per_run = max(1, int(options["max_per_run"]))
        selected: List = []
        skipped_cooldown: List[str] = []
        for shop in candidates:
            if not explicit_schemas and not options["skip_cooldown"] and in_failure_cooldown(shop.schema_name):
                skipped_cooldown.append(shop.schema_name)
                continue
            selected.append(shop)
            if len(selected) >= max_per_run:
                break

        if skipped_cooldown:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] Skipped {len(skipped_cooldown)} tenant(s) still in failure cooldown: "
                f"{', '.join(skipped_cooldown[:5])}"
                + (" ..." if len(skipped_cooldown) > 5 else "")
            ))

        if not selected:
            self.stdout.write(self.style.SUCCESS(
                "[CronProvision] All candidates are in failure cooldown. Nothing to do this tick."
            ))
            return

        self.stdout.write(self.style.NOTICE(
            f"[CronProvision] Selected {len(selected)} tenant(s) for this run: "
            f"{', '.join(s.schema_name for s in selected)}"
        ))

        # 3. Process each tenant ----------------------------------------
        summary: Dict[str, int] = {"ok": 0, "failed": 0, "skipped": 0}
        for shop in selected:
            try:
                ok = self._process_one(
                    shop=shop,
                    subprocess_python=subprocess_python,
                    subprocess_timeout=options["subprocess_timeout"],
                    dry_run=options["dry_run"],
                )
                if ok:
                    summary["ok"] += 1
                else:
                    summary["failed"] += 1
            except Exception as exc:
                logger.exception(
                    "[CronProvision] Unhandled error for '%s': %s", shop.schema_name, exc,
                )
                summary["failed"] += 1

        # 4. Print summary ----------------------------------------------
        msg = (
            f"[CronProvision] Done. ok={summary['ok']} failed={summary['failed']} "
            f"skipped={summary['skipped']}"
        )
        if summary["failed"]:
            self.stdout.write(self.style.ERROR(msg))
        else:
            self.stdout.write(self.style.SUCCESS(msg))

    # ------------------------------------------------------------------ #
    # Per-tenant processing                                               #
    # ------------------------------------------------------------------ #
    def _process_one(
        self,
        *,
        shop,
        subprocess_python: str,
        subprocess_timeout: int,
        dry_run: bool,
    ) -> bool:
        from system.account.migration_runner import (
            acquire_migration_lock,
            clear_failure_cooldown,
            in_failure_cooldown,
            release_migration_lock,
        )
        from system.core.models import Shop

        schema_name = (shop.schema_name or "").strip().lower()
        if not schema_name:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] Skipping row id={shop.id}: empty schema_name."
            ))
            return False

        # Dry-run short-circuit.
        if dry_run:
            cmd_preview = self._build_chunk_command(subprocess_python, schema_name)
            self.stdout.write(self.style.NOTICE(
                f"[CronProvision][DRY-RUN] {schema_name} (status={shop.provisioning_status})"
            ))
            self.stdout.write("    " + " ".join(cmd_preview))
            return True

        # Acquire lock (force=True — cron is highest authority).
        acquired = acquire_migration_lock(schema_name, force=True)
        if not acquired:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] Could not acquire lock for '{schema_name}'. Skipping."
            ))
            return False

        try:
            shop.refresh_from_db()
            if shop.provisioning_status == Shop.ProvisioningStatus.READY:
                self.stdout.write(self.style.SUCCESS(
                    f"[CronProvision] '{schema_name}' is already READY. Nothing to do."
                ))
                return True

            shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
            # Keep any prior progress message rather than overwriting with generic text
            if not (shop.provisioning_error or "").startswith("Migration "):
                shop.provisioning_error = "Cron sweep: preparing to apply migrations..."
            shop.save(update_fields=["provisioning_status", "provisioning_error"])

            self.stdout.write(self.style.NOTICE(
                f"[CronProvision] [{schema_name}] Marked IN_PROGRESS. Applying next migration..."
            ))

            # 0) Pre-flight: repair "lying" migration records.
            self._repair_lying_migration_records(shop, schema_name)

            # 1) Ensure schema + django_migrations table exist and shared
            #    migration records are seeded (so Django dependency resolution works).
            self._ensure_schema_bootstrapped(schema_name)

            # 2) Run exactly ONE migration as a subprocess.
            returncode, stdout_text, stderr_text = self._run_chunk_subprocess(
                subprocess_python=subprocess_python,
                schema_name=schema_name,
                timeout=subprocess_timeout,
            )

            # returncode semantics (set by run_tenant_chunked_migrations):
            #   0 = applied 1 migration, more remain
            #   1 = migration failure
            #   2 = all migrations already applied (complete)
            if returncode == 1:
                # Hard failure — extract meaningful error from output
                error_text = (stderr_text or stdout_text or "Migration subprocess failed.")[-2800:]
                self._mark_failed(shop, f"Migration subprocess failed for schema '{schema_name}':\n{error_text}")
                return False

            # Parse progress from subprocess stdout and persist to Shop.
            self._write_progress_from_output(shop, schema_name, stdout_text)

            complete = returncode == 2

            if complete:
                # All migrations applied — finalise.
                final = self._finalise_if_complete(shop, schema_name)
                if final == "ready":
                    clear_failure_cooldown(schema_name)
                    self.stdout.write(self.style.SUCCESS(
                        f"[CronProvision] [{schema_name}] All migrations applied. Finalised -> READY."
                    ))
                    return True
                if final == "failed":
                    return False
                # Finalisation returned "pending" (admin user table still missing etc.)
                # — next tick will retry.
                self.stdout.write(self.style.WARNING(
                    f"[CronProvision] [{schema_name}] Migrations complete but finalisation "
                    f"deferred; next cron tick will finish."
                ))
                return True

            # returncode == 0: one migration applied, more remain.
            self.stdout.write(self.style.NOTICE(
                f"[CronProvision] [{schema_name}] One migration applied. "
                f"Will continue next cron tick."
            ))
            return True

        finally:
            release_migration_lock(schema_name)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    # Critical tables each migration is expected to create.  When a table
    # is missing but its owning migration is recorded as applied, that row
    # is a lie and must be un-applied so the subprocess can re-run it.
    LYING_MIGRATION_TABLES = {
        ("pos", "0002_postransaction_authoritative_order_and_more"): "pos_catalog_items",
        ("userauth", "0001_initial"): "tenant_users",
    }

    def _repair_lying_migration_records(self, shop, schema_name: str) -> None:
        """Un-apply migration records whose tables do not actually exist."""
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder

        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SET search_path = "{schema_name}", "public"')
                recorder = MigrationRecorder(connection)
                applied = set(recorder.applied_migrations())
                if not applied:
                    return

                for (app_label, migration_name), table in self.LYING_MIGRATION_TABLES.items():
                    if (app_label, migration_name) not in applied:
                        continue
                    cursor.execute(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = %s AND table_name = %s",
                        [schema_name, table],
                    )
                    if cursor.fetchone():
                        continue  # table exists — record is honest

                    self.stdout.write(self.style.WARNING(
                        f"[CronProvision] [{schema_name}] {app_label}.{migration_name} recorded "
                        f"as applied but table '{table}' is missing - un-applying."
                    ))
                    recorder.record_unapplied(app_label, migration_name)
                    logger.warning(
                        "[CronProvision] Un-applied lying migration %s.%s for schema '%s' "
                        "(table %s missing).",
                        app_label, migration_name, schema_name, table,
                    )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Pre-flight repair check failed "
                f"(continuing anyway): {exc}"
            ))
        finally:
            try:
                connection.set_schema_to_public()
            except Exception:
                pass

    def _ensure_schema_bootstrapped(self, schema_name: str) -> None:
        """
        Ensures the tenant schema and its django_migrations table exist and that
        shared-app migration records are seeded in so Django's dependency resolver
        sees shared migrations (auth, contenttypes, etc.) as already satisfied.
        This is a fast no-op if the schema is already bootstrapped.
        """
        try:
            from system.account.migration_runner import _ensure_schema_exists
            _ensure_schema_exists(schema_name)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Schema bootstrap failed (continuing): {exc}"
            ))

    def _build_chunk_command(
        self,
        subprocess_python: str,
        schema_name: str,
    ) -> List[str]:
        """
        Build the single-migration subprocess command:
          run_tenant_chunked_migrations --schema=<name> --chunk-size=1 --max-chunks=1 --no-throttle
        """
        from django.conf import settings
        manage_py_path = str(settings.BASE_DIR / "manage.py")

        return [
            subprocess_python,
            manage_py_path,
            "run_tenant_chunked_migrations",
            f"--schema={schema_name}",
            "--chunk-size=1",
            "--max-chunks=1",
            "--no-throttle",
            "--force",
        ]

    def _run_chunk_subprocess(
        self,
        *,
        subprocess_python: str,
        schema_name: str,
        timeout: int,
    ) -> Tuple[int, str, str]:
        """
        Run the single-migration subprocess.
        Returns (returncode, stdout_text, stderr_text).
        """
        from django.conf import settings

        cmd = self._build_chunk_command(subprocess_python, schema_name)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        project_cwd = str(settings.BASE_DIR)

        self.stdout.write(self.style.NOTICE(
            f"[CronProvision] [{schema_name}] $ {' '.join(cmd)}"
        ))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=project_cwd,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            return 1, "", f"Could not launch subprocess: {exc}"
        except Exception as exc:
            return 1, "", f"Could not launch subprocess: {exc}"

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except Exception:
                stdout, stderr = "", ""
            return 1, stdout or "", (
                f"Subprocess timed out after {timeout}s for schema '{schema_name}'. "
                f"Partial stderr:\n{(stderr or '')[:1500]}"
            )

        # Log the output so it appears in the cron log.
        tail = (stdout or "")[-1500:]
        if tail.strip():
            self.stdout.write(self.style.NOTICE(
                f"[CronProvision] [{schema_name}] output:\n{tail}"
            ))

        return proc.returncode, stdout or "", stderr or ""

    def _write_progress_from_output(self, shop, schema_name: str, stdout_text: str) -> None:
        """
        Parse the progress line from run_tenant_chunked_migrations output and
        write it to Shop.provisioning_error so the UI polling endpoint can read
        live progress even before the tenant schema's django_migrations table is
        queryable.

        The subprocess emits lines like:
          PROGRESS:3/37:pos.0002_postransaction_authoritative_order_and_more
        """
        progress_msg = None
        for line in (stdout_text or "").splitlines():
            line = line.strip()
            if line.startswith("PROGRESS:"):
                # Format: PROGRESS:<applied>/<total>:<migration_label>
                rest = line[len("PROGRESS:"):]
                try:
                    counts_part, migration_label = rest.split(":", 1)
                    applied_str, total_str = counts_part.split("/", 1)
                    applied = int(applied_str)
                    total = int(total_str)
                    progress_msg = f"Migration {applied}/{total}: {migration_label}"
                except Exception:
                    progress_msg = f"Migration in progress: {rest}"

        if progress_msg:
            try:
                from system.core.models import Shop
                Shop.objects.filter(schema_name=schema_name).update(
                    provisioning_error=progress_msg[:2900]
                )
                self.stdout.write(self.style.NOTICE(
                    f"[CronProvision] [{schema_name}] Progress: {progress_msg}"
                ))
            except Exception as exc:
                logger.debug("[CronProvision] Could not write progress for '%s': %s", schema_name, exc)

    def _finalise_if_complete(self, shop, schema_name: str) -> str:
        """
        Post-migration finalisation ONLY — no migration execution.
        Returns "ready", "failed", or "pending".
        """
        from system.account.schema_inspector import get_tenant_migration_status

        # 1) Are migrations actually complete (real DB state)?
        try:
            mig_status = get_tenant_migration_status(schema_name, use_cache=False)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Could not inspect migration status: {exc}"
            ))
            return "pending"

        if not mig_status.get("is_ready"):
            return "pending"

        shop.refresh_from_db()

        # 2) Entitlements from the onboarding session.
        try:
            from system.account.models import OnboardingSession
            from system.account.services import TenantService
            session = (
                OnboardingSession.objects.filter(metadata__tenant_schema_name=schema_name)
                .exclude(status__in=[
                    OnboardingSession.Status.COMPLETED,
                    OnboardingSession.Status.CANCELLED,
                ])
                .order_by("-updated_at")
                .first()
            )
            if session:
                TenantService.provision_tenant_entitlements(session, shop)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Entitlement provisioning failed (non-fatal): {exc}"
            ))

        # 3) Tenant admin user.
        try:
            from system.account.sso import ensure_tenant_admin_user, TenantSchemaNotReady
            ensure_tenant_admin_user(shop, shop.owner)
        except TenantSchemaNotReady as exc:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Schema still not ready after migrate "
                f"({exc}); will re-repair and retry next tick."
            ))
            self._repair_lying_migration_records(shop, schema_name)
            return "pending"
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Could not provision tenant admin (non-fatal): {exc}"
            ))

        # 4) Seed defaults (theme, settings singletons).
        try:
            from system.account.migration_runner import _seed_tenant_defaults
            _seed_tenant_defaults(schema_name)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Defaults seeding failed (non-fatal): {exc}"
            ))

        # 5) Flip to READY.
        from system.account.migration_runner import _finalize_ready
        _finalize_ready(shop)

        # 6) Mark the onboarding session completed.
        try:
            from django.utils import timezone
            from system.account.models import OnboardingSession
            session = (
                OnboardingSession.objects.filter(metadata__tenant_schema_name=schema_name)
                .exclude(status__in=[
                    OnboardingSession.Status.COMPLETED,
                    OnboardingSession.Status.CANCELLED,
                ])
                .order_by("-updated_at")
                .first()
            )
            if session:
                metadata = dict(session.metadata or {})
                metadata["tenant_schema_name"] = schema_name
                metadata["provisioned_at"] = timezone.now().isoformat()
                metadata["provisioning_source"] = "cron_sweep"
                session.status = OnboardingSession.Status.COMPLETED
                session.completed_at = timezone.now()
                session.metadata = metadata
                session.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Could not mark onboarding session completed: {exc}"
            ))

        return "ready"

    def _mark_failed(self, shop, message: str) -> None:
        from system.account.migration_runner import set_failure_cooldown
        from system.core.models import Shop

        shop.refresh_from_db()
        shop.provisioning_status = Shop.ProvisioningStatus.FAILED
        shop.provisioning_error = message[:2900]
        shop.save(update_fields=["provisioning_status", "provisioning_error"])
        set_failure_cooldown(shop.schema_name)
        self.stdout.write(self.style.ERROR(
            f"[CronProvision] [{shop.schema_name}] Marked FAILED:\n{message}"
        ))
