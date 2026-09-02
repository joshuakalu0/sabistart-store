"""
system/account/management/commands/test_local_redis_runner.py
==============================================================
Smoke test for the local Redis-backed migration runner.

Usage:
    python manage.py test_local_redis_runner --schema <schema_name>

This command:
1. Checks Redis connectivity.
2. Writes/reads a test worker progress key.
3. Optionally launches a real background migration thread for the given schema.
"""

from __future__ import annotations

import time

from django.core.cache import cache
from django.core.management.base import BaseCommand
from system.account.worker_client import (
    clear_worker_progress,
    dispatch_migration_to_worker,
    get_worker_progress,
    set_worker_progress,
)


class Command(BaseCommand):
    help = "Smoke test the local Redis-backed migration runner."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            default="test_redis_runner_smoke",
            help="Schema name to use for the smoke test.",
        )
        parser.add_argument(
            "--run-migrations",
            action="store_true",
            default=False,
            help="Actually launch a background migration thread for the schema.",
        )

    def handle(self, *args, **options):
        schema_name = options["schema"].lower().strip()
        self.stdout.write(self.style.MIGRATE_HEADING(f"=== Local Redis Runner Smoke Test for '{schema_name}' ===\n"))

        # 1. Basic Redis connectivity
        try:
            cache.set("redis_runner_smoke_test", "ok", timeout=10)
            val = cache.get("redis_runner_smoke_test")
            cache.delete("redis_runner_smoke_test")
            if val != "ok":
                raise RuntimeError(f"Unexpected cache value: {val!r}")
            self.stdout.write(self.style.SUCCESS("Redis connectivity: OK"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Redis connectivity FAILED: {exc}"))
            return

        # 2. Set/read worker progress key
        try:
            set_worker_progress(schema_name, {
                "status": "RUNNING",
                "schema_name": schema_name,
                "applied_count": 0,
                "total_migrations": 0,
                "current_step": "smoke test",
                "progress_percentage": 1,
                "engine": "background_thread",
            })
            readback = get_worker_progress(schema_name)
            if not readback or readback.get("status") != "RUNNING":
                raise RuntimeError(f"Unexpected worker progress readback: {readback}")
            clear_worker_progress(schema_name)
            self.stdout.write(self.style.SUCCESS("Worker progress key round-trip: OK"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Worker progress key FAILED: {exc}"))
            return

        # 3. Optionally launch a real migration thread
        if options["run_migrations"]:
            from system.core.models import Shop

            shop = Shop.objects.filter(schema_name=schema_name).first()
            if not shop:
                self.stdout.write(self.style.WARNING(
                    f"Schema '{schema_name}' not found in Shop table; skipping live migration run."
                ))
                return

            self.stdout.write(f"Launching background migration thread for schema '{schema_name}'...")
            clear_worker_progress(schema_name)
            result = dispatch_migration_to_worker(shop, chunk_size=1)
            self.stdout.write(f"Dispatch result: {result}")

            self.stdout.write("Polling Redis for progress (Ctrl+C to stop)...")
            try:
                for _ in range(60):
                    progress = get_worker_progress(schema_name)
                    if not progress:
                        time.sleep(1)
                        continue
                    status = progress.get("status", "UNKNOWN")
                    pct = progress.get("progress_percentage", 0)
                    step = progress.get("current_step", "")
                    self.stdout.write(f"  [{status}] {pct}% — {step}")
                    if status in ("COMPLETED", "FAILED"):
                        break
                    time.sleep(2)
            except KeyboardInterrupt:
                self.stdout.write("\nStopped polling.")

        self.stdout.write(self.style.SUCCESS("\nSmoke test completed."))
