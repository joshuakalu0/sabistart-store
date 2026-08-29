"""
manage.py run_tenant_chunked_migrations
=======================================
Celery-free CLI command that applies pending tenant migrations in small,
resumable micro-chunks — safe for 1GB RAM hosts.

Examples:
    # All tenants that are not READY yet (one pass):
    python manage.py run_tenant_chunked_migrations

    # One specific tenant, max 3 chunks per run, stop after 20 seconds:
    python manage.py run_tenant_chunked_migrations --schema onboard_ab12cd34 --max-chunks 3 --time-budget 20

    # Continuous mode for maintenance windows (re-runs until everything is ready):
    python manage.py run_tenant_chunked_migrations --loop --sleep 3
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Apply pending tenant schema migrations in dependency-ordered micro-chunks "
        "without Celery. Each chunk commits individually, the DB connection is "
        "released between chunks, and failures record a checkpoint so reruns "
        "resume from the last successfully applied migration file."
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
            default=None,
            help="Max migrations per chunk (default: TENANT_PROVISIONING_CHUNK_SIZE setting or 1).",
        )

        parser.add_argument(
            "--max-chunks",
            type=int,
            default=None,
            help="Stop after applying this many chunks per schema (keeps each run bounded).",
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
            help="CPU safe threshold (percentage, default: 65.0). Below this runs without delay.",
        )
        parser.add_argument(
            "--cpu-warning",
            type=float,
            default=82.0,
            help="CPU warning threshold (percentage, default: 82.0). Above this injects adaptive sleep.",
        )
        parser.add_argument(
            "--cpu-critical",
            type=float,
            default=85.0,
            help="CPU critical threshold (percentage, default: 85.0). Above this enters backoff loop.",
        )
        parser.add_argument(
            "--ram-critical",
            type=float,
            default=85.0,
            help="RAM critical threshold (percentage, default: 85.0). Above this enters backoff loop.",
        )
        parser.add_argument(
            "--backoff-timeout",
            type=float,
            default=15.0,
            help="Maximum seconds to wait in backoff loop when system is under critical load (default: 15.0).",
        )

    def handle(self, *args, **options):
        from system.account.migration_runner import (
            acquire_migration_lock,
            release_migration_lock,
            run_chunked_tenant_migrations,
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
            self.stdout.write(self.style.SUCCESS("Nothing to do — every tenant is fully migrated."))
            return

        throttle_mode = "OFF" if options["no_throttle"] else f"ON (Safe <{options['cpu_safe']}%, Warn <{options['cpu_warning']}%, Crit >{options['cpu_critical']}%)"

        self.stdout.write(
            f"Migrating {len(schemas)} tenant schema(s) in micro-chunks "
            f"(chunk_size={options['chunk_size'] or 'default'}, "
            f"max_chunks={options['max_chunks'] or 'unlimited'}, "
            f"time_budget={options['time_budget'] or 'none'}s, "
            f"force={force_mode}, "
            f"throttling={throttle_mode})..."
        )

        max_passes = None if options["loop"] else 1
        pass_number = 0

        while max_passes is None or pass_number < max_passes:
            pass_number += 1
            if pass_number > 1:
                self.stdout.write(f"\n── Pass {pass_number} ──")

            unfinished = []
            for schema_name in schemas:
                self.stdout.write(f"\n▶ {schema_name}")

                # Check host metrics
                cpu, ram = throttler.get_metrics()
                status_label = throttler.assess_status(cpu, ram)
                self.stdout.write(f"  System Health: CPU {cpu:.1f}% | RAM {ram:.1f}% [{status_label}]")

                # Acquire migration lock (with force override if targeting specific schema)
                if not acquire_migration_lock(schema_name, force=force_mode):
                    self.stdout.write(self.style.WARNING(
                        f"  ⏸ {schema_name} is being migrated by another process — skipped."
                    ))
                    unfinished.append(schema_name)
                    continue

                try:
                    result = run_chunked_tenant_migrations(
                        schema_name,
                        chunk_size=options["chunk_size"],
                        max_chunks=options["max_chunks"],
                        time_budget=options["time_budget"],
                        throttler=throttler,
                    )
                finally:
                    release_migration_lock(schema_name)

                if result["failed_at"]:
                    checkpoint = result["failed_at"]
                    self.stdout.write(self.style.ERROR(
                        f"  ✖ FAILED at {checkpoint['app']}.{checkpoint['migration']} — "
                        f"checkpoint recorded. Error: {checkpoint['error']}"
                    ))
                    self.stdout.write("    Re-run the command after fixing the issue; it will "
                                      "resume from the last successfully applied migration file.")
                    continue

                applied_count = len(result["migrations_applied"])
                if applied_count:
                    self.stdout.write(f"  ✔ Applied {applied_count} migration(s) "
                                      f"in {result['chunks_applied']} chunk(s).")

                if result["completed"]:
                    self.stdout.write(self.style.SUCCESS(f"  ✔ {schema_name} is fully migrated."))
                else:
                    remaining = result.get("remaining", 0)
                    reason = result.get("stopped_reason") or "budget"
                    self.stdout.write(self.style.WARNING(
                        f"  ⏸ {schema_name}: {remaining} migration(s) still pending "
                        f"(stopped: {reason})."
                    ))
                    unfinished.append(schema_name)

            if not unfinished or max_passes == 1:
                break

            # Narrow subsequent passes to the schemas that still have work left.
            schemas = unfinished
            time.sleep(max(0.0, float(options["sleep"])))

        if unfinished:
            self.stdout.write(self.style.WARNING(
                f"\nFinished with {len(unfinished)} schema(s) still pending: "
                f"{', '.join(unfinished)}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS("\nAll selected tenants are fully migrated."))
