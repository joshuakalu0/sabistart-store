"""
manage.py run_tenant_chunked_migrations
=======================================
Celery-free CLI command that applies pending tenant migrations in small,
resumable micro-chunks — safe for 1GB RAM hosts.

Exit codes
----------
0 = Applied --max-chunks migrations; more migrations still remain.
    The cron parent will call this again next tick to continue.
1 = A migration failure occurred. Cron parent marks schema FAILED.
2 = All migrations already applied (nothing to do / schema is complete).
    The cron parent will finalise (READY, entitlements, admin user).

Progress lines (stdout)
-----------------------
After each migration the command emits a machine-readable line:
    PROGRESS:<applied>/<total>:<app>.<migration_name>

The cron parent parses these lines and writes them to
Shop.provisioning_error so the UI polling endpoint can show live
progress even before the tenant schema's django_migrations table is
directly queryable.

Examples
--------
    # One specific tenant, apply 1 migration:
    python manage.py run_tenant_chunked_migrations --schema onboard_ab12cd34 \\
        --chunk-size=1 --max-chunks=1 --no-throttle --force

    # All tenants that are not READY yet (one pass):
    python manage.py run_tenant_chunked_migrations

    # Continuous mode for maintenance windows (re-runs until everything is ready):
    python manage.py run_tenant_chunked_migrations --loop --sleep 3
"""

from __future__ import annotations

import sys
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Apply pending tenant schema migrations in dependency-ordered micro-chunks "
        "without Celery. Each chunk commits individually, the DB connection is "
        "released between chunks, and failures record a checkpoint so reruns "
        "resume from the last successfully applied migration file.\n\n"
        "Exit codes: 0=partial (more remain), 1=failure, 2=complete (all applied)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            action="append",
            default=[],
            help="Tenant schema name to migrate. Repeatable. Defaults to all tenants that are not READY.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=1,
            help="Max migrations per chunk (default: 1).",
        )
        parser.add_argument(
            "--max-chunks",
            type=int,
            default=1,
            help=(
                "Stop after applying this many chunks per schema. "
                "Default 1 (exactly one migration per invocation). "
                "Set to 0 for unlimited."
            ),
        )
        parser.add_argument(
            "--time-budget",
            type=float,
            default=None,
            help="Stop cleanly after this many seconds (checks between chunks only).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Include tenants already marked READY (re-checks for unapplied migrations).",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep processing until every selected tenant is fully migrated.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=2.0,
            help="Seconds to rest between loop passes (default 2) so the VM can breathe.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Force override and clear any existing migration lock on the target schema(s).",
        )
        parser.add_argument(
            "--no-throttle",
            action="store_true",
            default=False,
            help="Disable adaptive CPU and RAM throttling.",
        )
        parser.add_argument(
            "--cpu-safe",
            type=float,
            default=65.0,
            help="CPU safe threshold (percentage, default: 65.0).",
        )
        parser.add_argument(
            "--cpu-warning",
            type=float,
            default=82.0,
            help="CPU warning threshold (percentage, default: 82.0).",
        )
        parser.add_argument(
            "--cpu-critical",
            type=float,
            default=85.0,
            help="CPU critical threshold (percentage, default: 85.0).",
        )
        parser.add_argument(
            "--ram-critical",
            type=float,
            default=85.0,
            help="RAM critical threshold (percentage, default: 85.0).",
        )
        parser.add_argument(
            "--backoff-timeout",
            type=float,
            default=15.0,
            help="Maximum seconds to wait in backoff loop (default: 15.0).",
        )

    def handle(self, *args, **options):
        from system.account.migration_runner import (
            acquire_migration_lock,
            release_migration_lock,
            _ensure_schema_exists,
        )
        from system.account.throttler import AdaptiveThrottler
        from system.core.models import Shop

        throttler = AdaptiveThrottler(
            cpu_safe_limit=options["cpu_safe"],
            cpu_warning_limit=options["cpu_warning"],
            cpu_critical_limit=options["cpu_critical"],
            ram_critical_limit=options["ram_critical"],
            enabled=not options["no_throttle"],
        )

        schemas = [s.strip().lower() for s in options["schema"] if s.strip()]
        force_mode = options.get("force", False) or bool(schemas)

        if not schemas:
            queryset = Shop.objects.all() if options["all"] else Shop.objects.exclude(
                provisioning_status=Shop.ProvisioningStatus.READY
            )
            schemas = list(queryset.order_by("created_on").values_list("schema_name", flat=True))

        if not schemas:
            self.stdout.write(self.style.SUCCESS("Nothing to do - every tenant is fully migrated."))
            # Exit code 2 = complete (nothing to do)
            sys.exit(2)

        chunk_size = max(1, options["chunk_size"] or 1)
        max_chunks = options["max_chunks"]
        if max_chunks == 0:
            max_chunks = None  # unlimited

        self.stdout.write(
            f"[ChunkedMigrations] Migrating {len(schemas)} tenant schema(s) "
            f"(chunk_size={chunk_size}, max_chunks={max_chunks or 'unlimited'}, "
            f"force={force_mode}, throttle={'off' if options['no_throttle'] else 'on'})..."
        )

        max_loop_passes = None if options["loop"] else 1
        pass_number = 0
        any_failure = False
        all_complete = True

        while max_loop_passes is None or pass_number < max_loop_passes:
            pass_number += 1
            if pass_number > 1:
                self.stdout.write(f"\n-- Pass {pass_number} --")

            unfinished = []

            for schema_name in schemas:
                self.stdout.write(f"\n> {schema_name}")

                # Acquire migration lock
                if not acquire_migration_lock(schema_name, force=force_mode):
                    self.stdout.write(self.style.WARNING(
                        f"  [{schema_name}] is being migrated by another process - skipped."
                    ))
                    unfinished.append(schema_name)
                    all_complete = False
                    continue

                try:
                    schema_complete, schema_failed = self._migrate_schema(
                        schema_name=schema_name,
                        chunk_size=chunk_size,
                        max_chunks=max_chunks,
                        time_budget=options["time_budget"],
                        throttler=throttler,
                    )
                finally:
                    release_migration_lock(schema_name)

                if schema_failed:
                    any_failure = True
                    all_complete = False
                    self.stdout.write(self.style.ERROR(
                        f"  [{schema_name}] [FAIL] Migration FAILED - schema marked failed."
                    ))
                    # For single-schema runs, exit immediately with failure code
                    if len(schemas) == 1:
                        sys.exit(1)
                elif schema_complete:
                    self.stdout.write(self.style.SUCCESS(
                        f"  [{schema_name}] [OK] All migrations applied."
                    ))
                else:
                    all_complete = False
                    unfinished.append(schema_name)
                    self.stdout.write(self.style.WARNING(
                        f"  [{schema_name}] [PARTIAL] - will continue next cron tick."
                    ))

            if not unfinished or max_loop_passes == 1:
                break

            schemas = unfinished
            time.sleep(max(0.0, float(options["sleep"])))

        # Emit final summary
        if any_failure:
            self.stdout.write(self.style.ERROR(
                f"\n[ChunkedMigrations] Finished with failures."
            ))
            sys.exit(1)
        elif all_complete:
            self.stdout.write(self.style.SUCCESS(
                f"\n[ChunkedMigrations] All selected tenants are fully migrated."
            ))
            # Exit code 2 = complete
            sys.exit(2)
        else:
            remaining_schemas = ", ".join(unfinished) if unfinished else "some schemas"
            self.stdout.write(self.style.WARNING(
                f"\n[ChunkedMigrations] Partial pass complete. {remaining_schemas} still pending."
            ))
            # Exit code 0 = partial (more remain)
            sys.exit(0)

    def _migrate_schema(
        self,
        *,
        schema_name: str,
        chunk_size: int,
        max_chunks,
        time_budget,
        throttler,
    ):
        """
        Apply up to max_chunks migrations for schema_name.
        Returns (complete: bool, failed: bool).
        Emits PROGRESS:<applied>/<total>:<label> lines to stdout after each migration.
        """
        from system.account.migration_runner import (
            _ensure_schema_exists,
            _apply_chunk,
        )
        from system.account.schema_inspector import (
            get_tenant_migration_status,
            plan_micro_chunks,
        )
        import time as _time

        try:
            _ensure_schema_exists(schema_name)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"  [{schema_name}] Schema bootstrap warning: {exc}"
            ))

        status = get_tenant_migration_status(schema_name, use_cache=False)
        total_migrations = status["total_migrations"]
        applied_count = status["applied_count"]
        pending_count = status["pending_count"]

        if pending_count == 0:
            self.stdout.write(self.style.SUCCESS(
                f"  [{schema_name}] [OK] Already fully applied ({applied_count}/{total_migrations})."
            ))
            return True, False  # complete, not failed

        chunks = plan_micro_chunks(schema_name, max_chunk_size=chunk_size)
        if not chunks:
            self.stdout.write(self.style.SUCCESS(
                f"  [{schema_name}] [OK] No pending chunks found."
            ))
            return True, False

        started_at = _time.monotonic()
        chunks_applied = 0

        for index, chunk in enumerate(chunks):
            # Check limits
            if max_chunks is not None and chunks_applied >= max_chunks:
                self.stdout.write(
                    f"  [{schema_name}] Reached max_chunks={max_chunks}. Stopping."
                )
                break

            if time_budget is not None and (_time.monotonic() - started_at) >= time_budget:
                self.stdout.write(
                    f"  [{schema_name}] Time budget exhausted. Stopping."
                )
                break

            # Throttle check
            if throttler is not None:
                health = throttler.throttle_before_chunk(max_backoff_seconds=15.0)
                if not health.is_safe_to_proceed:
                    self.stdout.write(self.style.WARNING(
                        f"  [{schema_name}] Critical system load - stopping early."
                    ))
                    break

            migration_list = chunk["migrations"]
            for app_label, migration_name in migration_list:
                self.stdout.write(
                    f"  [{schema_name}] Applying {app_label}.{migration_name}..."
                )
                try:
                    _apply_chunk(schema_name, [(app_label, migration_name)])
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(
                        f"  [{schema_name}] [FAIL]: {app_label}.{migration_name}: {exc}"
                    ))
                    # Emit PROGRESS line before failing so cron parent has data
                    new_status = get_tenant_migration_status(schema_name, use_cache=False)
                    new_applied = new_status["applied_count"]
                    self.stdout.write(
                        f"PROGRESS:{new_applied}/{total_migrations}:{app_label}.{migration_name}_FAILED"
                    )
                    return False, True  # not complete, failed

                # Migration succeeded — get fresh counts and emit PROGRESS line
                new_status = get_tenant_migration_status(schema_name, use_cache=False)
                new_applied = new_status["applied_count"]
                label = f"{app_label}.{migration_name}"
                # Machine-readable progress line parsed by process_pending_tenants
                self.stdout.write(f"PROGRESS:{new_applied}/{total_migrations}:{label}")
                self.stdout.write(self.style.SUCCESS(
                    f"  [{schema_name}] [OK] {label} ({new_applied}/{total_migrations})"
                ))

            chunks_applied += 1

        # Check final state
        final_status = get_tenant_migration_status(schema_name, use_cache=False)
        complete = final_status["is_ready"]
        remaining = final_status["pending_count"]

        if complete:
            self.stdout.write(self.style.SUCCESS(
                f"  [{schema_name}] [OK] All {final_status['applied_count']}/{total_migrations} migrations applied."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"  [{schema_name}] [PARTIAL] {final_status['applied_count']}/{total_migrations} applied, "
                f"{remaining} remaining."
            ))

        return complete, False
