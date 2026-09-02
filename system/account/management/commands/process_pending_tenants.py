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
--------------------------------
1. SELECTs the oldest Shop rows whose ``provisioning_status`` is
   ``PENDING`` / ``PROVISIONING`` / ``IN_PROGRESS`` / ``FAILED``
   (subject to the failure-cooldown gate).
2. Acquires the per-schema migration lock so it does not collide with
   the in-process worker if both happen to be running.
3. Flips ``provisioning_status`` to ``IN_PROGRESS``.
4. Runs ``python manage.py migrate_schemas`` (well, ``migrate`` with
   ``--schema=<name>`` -- django-tenants exposes the migration runner
   through the stock ``migrate`` command since v3.x) as a *subprocess*
   so the DDL executes in a brand-new OS process with its own memory
   budget. The subprocess's stderr/stdout are captured and persisted
   to ``Shop.provisioning_error`` on failure.
5. If the subprocess succeeded, calls ``advance_tenant_provisioning``
   *in-process* to run the cheap post-migration steps: grant
   entitlements for the onboarding session, create the tenant admin
   user, and flip ``provisioning_status`` to ``READY``.
6. On any failure: flips the row to ``FAILED`` with the captured
   subprocess output, sets the failure-cooldown so we don't busy-loop
   on a broken schema.
7. Releases the lock and moves on to the next pending tenant.
8. Stops after ``--max-per-run`` tenants (default 1) so a single cron
   tick can never starve the rest of the system.

Key properties
--------------
* One tenant at a time. No concurrency. Deliberate.
* Each failed tenant is isolated -- a broken migration in tenant A
  never blocks tenant B.
* Idempotent: re-running on the same set just picks up where the last
  run stopped.
* Honors the failure-cooldown used by the in-process runner, so this
  command and the worker can coexist without hammering a broken
  schema.

Example usage
-------------
    # Local dry-run (does not change anything; just prints what would
    # be processed). Safe to run on Windows.
    python manage.py process_pending_tenants --dry-run

    # Process up to 3 pending tenants, redirecting output to a log.
    python manage.py process_pending_tenants --max-per-run 3 \\
        >> /var/log/sabistart/provision.log 2>&1

    # Process a single specific schema by hand (debugging).
    python manage.py process_pending_tenants --schema onboard_ab12cd34

Cron entry (Linux VM)
---------------------
    */3 * * * * /home/sabistart/.venv/bin/python \\
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


# Statuses that mean "this tenant still needs work".  PENDING and
# PROVISIONING are the freshly-created states; IN_PROGRESS means a
# previous run was interrupted; FAILED is retried on a cooldown.
_PENDING_STATUSES = (
    "pending",
    "provisioning",
    "in_progress",
    "failed",
)

# Subprocess hard timeout per schema.  Generous because some tenants
# have 30+ migrations.  Set on the lower end by --time-budget if the
# caller wants stricter behaviour.
DEFAULT_SUBPROCESS_TIMEOUT = 900  # 15 minutes


class Command(BaseCommand):
    help = (
        "Cron-driven, OS-isolated sweep that migrates pending tenant "
        "schemas in a separate process and finalises their provisioning "
        "(entitlements, tenant admin user, READY status). One tenant at "
        "a time. Safe to run on a 1 vCPU / 1 GB host."
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
                "Default 1 -- one tenant per cron tick, on purpose, so the "
                "host can breathe."
            ),
        )
        parser.add_argument(
            "--subprocess-timeout",
            type=int,
            default=DEFAULT_SUBPROCESS_TIMEOUT,
            help=(
                "Hard wall-clock timeout (seconds) for the migrate "
                "subprocess per tenant. Default 900 (15 min)."
            ),
        )
        parser.add_argument(
            "--migrate-args",
            default="",
            help=(
                "Extra arguments to forward to the migrate subprocess, "
                "e.g. '--no-input --fake-initial'.  Quoted as a single "
                "string; the command will split on whitespace."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Print which tenants would be processed and the exact "
                "subprocess command that would run, but do not change "
                "any state.  Use this to verify the cron wiring before "
                "letting it run for real."
            ),
        )
        parser.add_argument(
            "--skip-cooldown",
            action="store_true",
            help=(
                "Override the failure-cooldown gate so FAILED tenants "
                "are retried immediately.  Off by default so a broken "
                "schema does not get hammered on every cron tick."
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

        # Resolve the venv's python so the subprocess uses the same
        # interpreter that this management command is running under.
        # On the VM this is /home/sabistart/.venv/bin/python; locally
        # it's whatever is on PATH (sys.executable).
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
                    extra_migrate_args=options["migrate_args"],
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
        extra_migrate_args: str,
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

        # Dry-run short-circuit -- print and exit without changing state.
        if dry_run:
            cmd_preview = self._build_migrate_command(
                subprocess_python, schema_name, extra_migrate_args,
            )
            self.stdout.write(self.style.NOTICE(
                f"[CronProvision][DRY-RUN] {schema_name} (status={shop.provisioning_status})"
            ))
            self.stdout.write("    " + " ".join(cmd_preview))
            return True

        # Acquire lock (force=True because the cron is the highest
        # authority; if it runs, the previous in-process runner must
        # yield).
        acquired = acquire_migration_lock(schema_name, force=True)
        if not acquired:
            # This should not happen with force=True, but guard anyway.
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] Could not acquire lock for '{schema_name}'. Skipping."
            ))
            return False

        try:
            # Flip status so the UI / worker-client know we own this row.
            shop.refresh_from_db()
            if shop.provisioning_status == Shop.ProvisioningStatus.READY:
                self.stdout.write(self.style.SUCCESS(
                    f"[CronProvision] '{schema_name}' is already READY. Nothing to do."
                ))
                return True

            shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
            shop.provisioning_error = "Cron sweep: migration subprocess starting..."
            shop.save(update_fields=["provisioning_status", "provisioning_error"])

            self.stdout.write(self.style.NOTICE(
                f"[CronProvision] [{schema_name}] Marked IN_PROGRESS. Spawning migrate subprocess..."
            ))

            # 1) Subprocess: run the actual DDL in a separate OS process.
            ok, stderr_text, returncode = self._run_migrate_subprocess(
                subprocess_python=subprocess_python,
                schema_name=schema_name,
                extra_migrate_args=extra_migrate_args,
                timeout=subprocess_timeout,
            )

            if not ok:
                self._mark_failed(
                    shop,
                    f"migrate subprocess failed (returncode={returncode}) for schema '{schema_name}':\n"
                    f"{stderr_text[:2800]}",
                )
                return False

            self.stdout.write(self.style.SUCCESS(
                f"[CronProvision] [{schema_name}] Migrate subprocess succeeded."
            ))

            shop.refresh_from_db()
            if shop.provisioning_status == Shop.ProvisioningStatus.READY:
                clear_failure_cooldown(schema_name)
                # Seed theme + settings even when the subprocess finalised the shop.
                try:
                    from system.account.migration_runner import _seed_tenant_defaults
                    _seed_tenant_defaults(schema_name)
                except Exception as seed_exc:
                    self.stdout.write(self.style.WARNING(
                        f"[CronProvision] [{schema_name}] Seeding defaults failed (non-fatal): {seed_exc}"
                    ))
                self.stdout.write(self.style.SUCCESS(
                    f"[CronProvision] [{schema_name}] Finalised -- status is READY."
                ))
                return True


            # 2) In-process fallback: run the cheap finalisation step if needed.
            from system.account.migration_runner import (
                advance_tenant_provisioning,
                clear_failure_cooldown,
            )

            outcome = advance_tenant_provisioning(
                schema_name,
                source="cron_sweep",
            )

            if outcome.get("is_ready"):
                clear_failure_cooldown(schema_name)
                self.stdout.write(self.style.SUCCESS(
                    f"[CronProvision] [{schema_name}] Finalised -- status is READY."
                ))
                return True


            if outcome.get("failed"):
                self._mark_failed(
                    shop,
                    f"Finalisation failed for '{schema_name}': {outcome.get('error', '')[:2800]}",
                )
                return False

            # Partial / cooldown / locked -- treat as transient.  Do
            # NOT mark as FAILED; the next cron tick will pick it up.
            self.stdout.write(self.style.WARNING(
                f"[CronProvision] [{schema_name}] Finalisation did not complete "
                f"(is_ready={outcome.get('is_ready')}, cooldown={outcome.get('cooldown')}, "
                f"locked={outcome.get('locked')}). Will retry next tick."
            ))
            shop.refresh_from_db()
            shop.provisioning_error = (
                f"Partial: {outcome.get('error', '')[:800] or 'no error message; will retry next cron tick.'}"
            )
            shop.save(update_fields=["provisioning_error"])
            return True  # not a hard failure -- next tick handles it

        finally:
            release_migration_lock(schema_name)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _build_migrate_command(
        self,
        subprocess_python: str,
        schema_name: str,
        extra_migrate_args: str,
    ) -> List[str]:
        # ``migrate --schema=<name>`` is the django-tenants 3.x way to
        # apply a single tenant's migrations.  --noinput avoids prompts.
        # We do NOT pass --run-syncdb here; the chunked runner uses the
        # executor and we want consistent behaviour.
        #
        from django.conf import settings
        manage_py_path = str(settings.BASE_DIR / "manage.py")

        cmd = [
            subprocess_python,
            manage_py_path,
            "run_tenant_chunked_migrations",
            f"--schema={schema_name}",
            "--force",
            "--no-throttle",
        ]
        if extra_migrate_args:
            cmd.extend(extra_migrate_args.split())
        return cmd


    def _run_migrate_subprocess(
        self,
        *,
        subprocess_python: str,
        schema_name: str,
        extra_migrate_args: str,
        timeout: int,
    ) -> Tuple[bool, str, int]:
        """Run the migrate subprocess.  Returns (ok, stderr_text, returncode)."""
        from django.conf import settings

        cmd = self._build_migrate_command(subprocess_python, schema_name, extra_migrate_args)

        # Make sure the subprocess inherits the venv on PATH and
        # runs in the project root directory (where manage.py lives).
        env = os.environ.copy()
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
            )

        except FileNotFoundError as exc:
            return False, f"Could not launch subprocess: {exc}", -1
        except Exception as exc:
            return False, f"Could not launch subprocess: {exc}", -1

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except Exception:
                stdout, stderr = "", ""
            return False, (
                f"Subprocess timed out after {timeout}s for schema '{schema_name}'. "
                f"Partial stderr:\n{(stderr or '')[:1500]}"
            ), -9

        # Surface a tail of stdout to the cron log so a human can see
        # which migrations were applied.
        tail = (stdout or "")[-2000:]
        if tail.strip():
            self.stdout.write(self.style.NOTICE(
                f"[CronProvision] [{schema_name}] output:\n{tail}"
            ))

        if proc.returncode == 0:
            return True, stderr or "", proc.returncode
        return False, (stderr or stdout or "")[-4000:], proc.returncode

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

