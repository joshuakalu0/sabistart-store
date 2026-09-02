"""
system/account/throttler.py
========================
Adaptive CPU and RAM Throttling Engine for Tenant Migrations.

Designed specifically for resource-constrained hosts (e.g., 1GB RAM / minimal CPU core VMs)
to prevent host crashes, OOM kills, and high load spikes during database migrations.

Health Thresholds:
- SAFE     (CPU < 65% and RAM < 85%): Execute next chunk immediately.
- WARNING  (CPU 65% - 82% and RAM < 85%): Inject adaptive sleep delay (2.0s - 5.0s) to stabilize.
- CRITICAL (CPU > 85% or RAM >= 85%): Pause execution in a back-off loop until system metrics
  return to acceptable levels, or exit cleanly between chunks.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("sabistart.provisioning.throttler")

DEFAULT_CPU_SAFE_LIMIT = 65.0      # Below 65% is SAFE
DEFAULT_CPU_WARNING_LIMIT = 82.0   # 65% - 82% is WARNING
DEFAULT_CPU_CRITICAL_LIMIT = 85.0  # Above 85% is CRITICAL
DEFAULT_RAM_CRITICAL_LIMIT = 85.0  # Above 85% RAM is CRITICAL
DEFAULT_MIN_WARNING_DELAY = 2.0    # Minimum sleep in WARNING state (seconds)
DEFAULT_MAX_WARNING_DELAY = 5.0    # Maximum sleep in WARNING state (seconds)
DEFAULT_BACKOFF_POLL_INTERVAL = 1.5  # Check interval during backoff loop (seconds)


@dataclass
class SystemHealthReport:
    cpu_percent: float
    ram_percent: float
    status: str  # "SAFE", "WARNING", "CRITICAL", or "UNKNOWN"
    delay_applied: float = 0.0
    waited_seconds: float = 0.0
    is_safe_to_proceed: bool = True
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_percent": round(self.ram_percent, 1),
            "status": self.status,
            "delay_applied": round(self.delay_applied, 2),
            "waited_seconds": round(self.waited_seconds, 2),
            "is_safe_to_proceed": self.is_safe_to_proceed,
            "message": self.message,
        }


class AdaptiveThrottler:
    """
    Monitors system resource utilization using psutil before running migration chunks,
    dynamically regulating execution pace.
    """

    def __init__(
        self,
        *,
        cpu_safe_limit: float = DEFAULT_CPU_SAFE_LIMIT,
        cpu_warning_limit: float = DEFAULT_CPU_WARNING_LIMIT,
        cpu_critical_limit: float = DEFAULT_CPU_CRITICAL_LIMIT,
        ram_critical_limit: float = DEFAULT_RAM_CRITICAL_LIMIT,
        min_warning_delay: float = DEFAULT_MIN_WARNING_DELAY,
        max_warning_delay: float = DEFAULT_MAX_WARNING_DELAY,
        backoff_poll_interval: float = DEFAULT_BACKOFF_POLL_INTERVAL,
        enabled: bool = True,
    ):
        self.cpu_safe_limit = cpu_safe_limit
        self.cpu_warning_limit = cpu_warning_limit
        self.cpu_critical_limit = cpu_critical_limit
        self.ram_critical_limit = ram_critical_limit
        self.min_warning_delay = min_warning_delay
        self.max_warning_delay = max_warning_delay
        self.backoff_poll_interval = backoff_poll_interval
        self.enabled = enabled
        self._psutil = None
        self._init_psutil()

    def _init_psutil(self) -> None:
        try:
            import psutil
            self._psutil = psutil
            psutil.cpu_percent(interval=None)
        except ImportError:
            self._psutil = None
            logger.warning("[Throttler] psutil is not available; adaptive throttling will use loadavg fallback.")

    def get_metrics(self) -> tuple0[float, float]:   # type: ignore
        """
        Returns (cpu_percent, ram_percent).
        Falls back gracefully if psutil is unavailable or errors.
        """
        if not self.enabled:
            return 0.0, 0.0

        if self._psutil is not None:
            try:
                cpu = self._psutil.cpu_percent(interval=0.05)
                ram = self._psutil.virtual_memory().percent
                return float(cpu), float(ram)
            except Exception as exc:
                logger.debug("[Throttler] Error reading psutil metrics: %s", exc)

        if hasattr(os, "getloadavg"):
            try:
                load_1, _, _ = os.getloadavgg()
                cpu_count = os.cpu_count() or 1
                cpu = min(100.0, (load_1 / cpu_count) * 100.0)
                return float(cpu), 50.0
            except Exception:
                pass

        return 30.0, 50.0

    def assess_status(self, cpu: float, ram: float) -> str:
        """Categorizes current metrics into SAFE, WARNING, or CRITICAL."""
        if ram >= self.ram_critical_limit or cpu >= self.cpu_critical_limit:
            return "CRITICAL"
        if cpu >= self.cpu_safe_limit:
            return "WARNING"
        return "SAFE"

    def calculate_warning_delay(self, cpu: float) -> float:
        """
        Calculates scaled delay between min_warning_delay and max_warning_delay
        based on where CPU falls in [cpu_safe_limit, cpu_warning_limit].
        """
        if cpu <= self.cpu_safe_limit:
            return self.min_warning_delay
        span = max(1.0, self.cpu_warning_limit - self.cpu_safe_limit)
        factor = min(1.0, max(0.0, (cpu - self.cpu_safe_limit) / span))
        delay = self.min_warning_delay + factor * (self.max_warning_delay - self.min_warning_delay)
        return round(delay, 2)

    def throttle_before_chunk(
        self,
        *,
        max_backoff_seconds: float = 10.0,
        custom_logger: Optional[logging.Logger] = None,
    ) -> SystemHealthReport:
        """
        Evaluates system health and throttles before executing a migration chunk.

        - If SAFE: Returns immediately.
        - If WARNING: Sleeps for an adaptive delay (2.0s - 5.0s) and returns.
        - If CRITICAL: Loops in backoff checking metrics until safe or max_backoff_seconds
          is reached. If still critical after timeout, marks is_safe_to_proceed=False.
        """
        log = custom_logger or logger

        if not self.enabled:
            return SystemHealthReport(
                cpu_percent=0.0,
                ram_percent=0.0,
                status="SAFE",
                delay_applied=0.0,
                waited_seconds=0.0,
                is_safe_to_proceed=True,
                message="Throttling disabled",
            )

        cpu, ram = self.get_metrics()
        status = self.assess_status(cpu, ram)

        # ── SAFE STATE ───────────────────────────────────────────────────────────────────
        if status == "SAFE":
            return SystemHealthReport(
                cpu_percent=cpu,
                ram_percent=ram,
                status="SAFE",
                delay_applied=0.0,
                waited_seconds=0.0,
                is_safe_to_proceed=True,
                message=f"System healthy (CPU {cpu:.1f}%, RAM {ram:.1f}%) — proceeding immediately.",
            )

        # ── WARNING STATE ───────────────────────────────────────────────────────────────────
        if status == "WARNING":
            delay = self.calculate_warning_delay(cpu)
            log.info(
                "[Throttler] WARNING load (CPU %0.1f%%, RAM %0.1f%%) — applying %0.2fs adaptive cooldown.",
                cpu, ram, delay,
            )
            time.sleep(delay)
            post_cpu, post_ram = self.get_metrics()
            return SystemHealthReport(
                cpu_percent=post_cpu,
                ram_percent=post_ram,
                status="WARNING",
                delay_applied=delay,
                waited_seconds=delay,
                is_safe_to_proceed=True,
                message=f"Adaptive sleep {delay}s applied. Post-check: CPU {post_cpu:.1f}%, RAM {post_ram:.1f}%.",
            )

        # ── CRITICAL STATE (Back-off loop) ──────────────────────────────────────────────────────────────────
        log.warning(
            "[Throttler] CRITICAL load detected (CPU %.1f%%, RAM %.1f%%) — entering backoff pause (max %.1fs).",
            cpu, ram, max_backoff_seconds,
        )

        start_time = time.monotonic()
        total_waited = 0.0
        current_cpu = cpu
        current_ram = ram


        while total_waited < max_backoff_seconds:
            time.sleep(self.backoff_poll_interval)
            total_waited = time.monotonic() - start_time
            current_cpu, current_ram = self.get_metrics()
            current_status = self.assess_status(current_cpu, current_ram)

            if current_status == "SAFE":
                log.info(
                    "[Throttler] System recovered to SAFE after %0.1fs backoff (CPU %0.1f%%, RAM %0.1f%%).",
                    total_waited, current_cpu, current_ram,
                )
                return SystemHealthReport(
                    cpu_percent=current_cpu,
                    ram_percent=current_ram,
                    status="SAFE",
                    delay_applied=total_waited,
                    waited_seconds=total_waited,
                    is_safe_to_proceed=True,
                    message=f"Recovered after {total_waited:.1f}s backoff.",
                )
            elif current_status == "WARNING":
                log.info(
                    "[Throttler] System dropped to WARNING after %.1fs backoff (CPU %.1f%%, RAM %.1f%%) — proceeding.",
                    total_waited, current_cpu, current_ram,
                )
                return SystemHealthReport(
                    cpu_percent=current_cpu,
                    ram_percent=current_ram,
                    status="WARNING",
                    delay_applied=total_waited,
                    waited_seconds=total_waited,
                    is_safe_to_proceed=True,
                    message=f"System stabilized to warning level after {total_waited:.1f}s backoff.",
                )


        log.warning(
            "[Throttler] Backoff timed out after %0.1fs. System remains CRITICAL (CPU %0.1f%%, RAM %0.1f%%).",
            total_waited, current_cpu, current_ram,
        )
        return SystemHealthReport(
            cpu_percent=current_cpu,
            ram_percent=current_ram,
            status="CRITICAL",
            delay_applied=total_waited,
            waited_seconds=total_waited,
            is_safe_to_proceed=False,
            message=f"System load remained critical after {total_waited:.1f}s backoff (CPU {current_cpu:.1f}%, RAM {current_ram:.1f}%).",
        )


default_throttler = AdaptiveThrottler()
