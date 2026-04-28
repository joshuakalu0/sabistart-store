from __future__ import annotations

from dataclasses import dataclass
from functools import wraps

from django.contrib import messages
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import F, Q, Sum
from django.shortcuts import redirect
from django.utils import timezone

from dashboard.feature_marketplace.integration_registry import RESOURCE_COUNTERS
from dashboard.feature_marketplace.models import ResourceQuota, TenantEntitlement, UsageRecord
from system.feature_marketplace.models import FeatureDefinition, FeatureType, TenantFeatureOverride


FEATURE_CACHE_TTL = 300
QUOTA_CACHE_TTL = 60
GLOBAL_CACHE_TTL = 600


class FeatureAccessError(PermissionError):
    pass


class QuotaExceededError(FeatureAccessError):
    pass


class UsageBalanceError(FeatureAccessError):
    pass


def _schema_name() -> str:
    return getattr(connection, "schema_name", "public")


@dataclass
class FeatureAccessSnapshot:
    feature_code: str
    feature_type: str
    active: bool
    limit: int = 0
    used: int = 0
    remaining: int = 0
    source: str = ""


class FeatureEntitlementEngine:
    def __init__(self, schema_name: str | None = None):
        self.schema_name = schema_name or _schema_name()

    def _key(self, section: str, feature_code: str = "") -> str:
        suffix = f":{feature_code}" if feature_code else ""
        return f"feature_marketplace:{self.schema_name}:{section}{suffix}"

    def invalidate_cache(self, feature_code: str | None = None):
        if feature_code:
            cache.delete_many(
                [
                    self._key("bool", feature_code),
                    self._key("limit", feature_code),
                    self._key("usage", feature_code),
                    self._key("snapshot", feature_code),
                    self._key("tenant_override", feature_code),
                ]
            )
        cache.delete(self._key("all"))

    def _feature(self, feature_code: str) -> FeatureDefinition | None:
        try:
            return FeatureDefinition.objects.get(code=feature_code, is_active=True)
        except FeatureDefinition.DoesNotExist:
            return None

    def _global_override(self, feature_code: str):
        key = self._key("global", feature_code)
        cached = cache.get(key)
        if cached is not None:
            return cached
        feature = self._feature(feature_code)
        if feature is None:
            cache.set(key, False, GLOBAL_CACHE_TTL)
            return False
        if feature.is_globally_disabled:
            cache.set(key, False, GLOBAL_CACHE_TTL)
            return False
        if feature.is_globally_enabled:
            cache.set(key, True, GLOBAL_CACHE_TTL)
            return True
        cache.set(key, "inherit", GLOBAL_CACHE_TTL)
        return "inherit"

    def _tenant_override(self, feature_code: str):
        if not self.schema_name or self.schema_name == "public":
            return None
        key = self._key("tenant_override", feature_code)
        cached = cache.get(key)
        if cached is not None:
            return cached
        now = timezone.now()
        override = (
            TenantFeatureOverride.objects.filter(
                schema_name=self.schema_name,
                feature__code=feature_code,
                is_active=True,
            )
            .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=now))
            .filter(Q(effective_until__isnull=True) | Q(effective_until__gte=now))
            .order_by("-created_at")
            .first()
        )
        cache.set(key, override, FEATURE_CACHE_TTL)
        return override

    def has_feature(self, feature_code: str) -> bool:
        feature = self._feature(feature_code)
        if feature is None:
            return False
        override = self._global_override(feature_code)
        if override is True:
            return True
        if override is False:
            return False
        tenant_override = self._tenant_override(feature_code)
        if tenant_override is not None:
            if tenant_override.mode == tenant_override.OverrideMode.FORCE_DISABLED:
                return False
            if tenant_override.mode in {
                tenant_override.OverrideMode.FORCE_ENABLED,
                tenant_override.OverrideMode.FREE,
            }:
                return True
        if feature.feature_type == FeatureType.LIMIT:
            return self.get_feature_limit(feature_code) > 0
        if feature.feature_type == FeatureType.USAGE:
            return self.get_usage_remaining(feature_code) > 0
        key = self._key("bool", feature_code)
        cached = cache.get(key)
        if cached is not None:
            return cached
        now = timezone.now()
        value = TenantEntitlement.objects.filter(
            feature_code=feature_code,
            feature_type=FeatureType.BOOLEAN,
            status=TenantEntitlement.Status.ACTIVE,
            boolean_value=True,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).exists()
        if not value:
            value = feature.default_boolean_value
        cache.set(key, value, FEATURE_CACHE_TTL)
        return value

    def get_feature_limit(self, feature_code: str) -> int:
        feature = self._feature(feature_code)
        if feature is None:
            return 0
        override = self._global_override(feature_code)
        if override is False:
            return 0
        tenant_override = self._tenant_override(feature_code)
        if tenant_override is not None and tenant_override.mode == tenant_override.OverrideMode.FORCE_DISABLED:
            return 0
        key = self._key("limit", feature_code)
        cached = cache.get(key)
        if cached is not None:
            return cached
        now = timezone.now()
        total = TenantEntitlement.objects.filter(
            feature_code=feature_code,
            feature_type=FeatureType.LIMIT,
            status=TenantEntitlement.Status.ACTIVE,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).aggregate(total=Sum("limit_value"))["total"] or 0
        total += feature.default_limit_value
        cache.set(key, total, QUOTA_CACHE_TTL)
        return int(total)

    def get_usage_remaining(self, feature_code: str) -> int:
        feature = self._feature(feature_code)
        if feature is None:
            return 0
        override = self._global_override(feature_code)
        if override is False:
            return 0
        tenant_override = self._tenant_override(feature_code)
        if tenant_override is not None and tenant_override.mode == tenant_override.OverrideMode.FORCE_DISABLED:
            return 0
        key = self._key("usage", feature_code)
        cached = cache.get(key)
        if cached is not None:
            return cached
        now = timezone.now()
        totals = TenantEntitlement.objects.filter(
            feature_code=feature_code,
            feature_type=FeatureType.USAGE,
            status=TenantEntitlement.Status.ACTIVE,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).aggregate(
            granted=Sum("quantity_granted"),
            used=Sum("quantity_used"),
        )
        remaining = feature.default_usage_value + max(0, (totals["granted"] or 0) - (totals["used"] or 0))
        cache.set(key, remaining, QUOTA_CACHE_TTL)
        return int(remaining)

    def get_usage_snapshot(self, feature_code: str) -> FeatureAccessSnapshot:
        feature = self._feature(feature_code)
        if feature is None:
            return FeatureAccessSnapshot(feature_code=feature_code, feature_type="", active=False)
        if feature.feature_type == FeatureType.LIMIT:
            total = self.get_feature_limit(feature_code)
            quota = ResourceQuota.objects.filter(resource_type=feature_code).first()
            used = quota.used_quota if quota else 0
            return FeatureAccessSnapshot(feature_code, feature.feature_type, total > 0, total, used, max(0, total - used))
        if feature.feature_type == FeatureType.USAGE:
            remaining = self.get_usage_remaining(feature_code)
            return FeatureAccessSnapshot(feature_code, feature.feature_type, remaining > 0, remaining=remaining)
        return FeatureAccessSnapshot(feature_code, feature.feature_type, self.has_feature(feature_code))

    def get_all_entitlements(self) -> dict[str, FeatureAccessSnapshot]:
        cached = cache.get(self._key("all"))
        if cached is not None:
            return cached
        payload = {}
        for feature in FeatureDefinition.objects.filter(is_active=True).order_by("display_order", "name"):
            payload[feature.code] = self.get_usage_snapshot(feature.code)
        cache.set(self._key("all"), payload, FEATURE_CACHE_TTL)
        return payload

    def rebuild_quota(self, feature_code: str) -> ResourceQuota:
        total_quota = self.get_feature_limit(feature_code)
        counter = RESOURCE_COUNTERS.get(feature_code)
        used_quota = counter() if counter else 0
        quota, _ = ResourceQuota.objects.update_or_create(
            resource_type=feature_code,
            defaults={"total_quota": total_quota, "used_quota": used_quota},
        )
        self.invalidate_cache(feature_code)
        return quota

    def rebuild_all_quotas(self):
        for feature_code in RESOURCE_COUNTERS:
            self.rebuild_quota(feature_code)

    @transaction.atomic
    def consume_feature_usage(self, feature_code: str, amount: int = 1, description: str = "", metadata: dict | None = None) -> bool:
        if amount <= 0:
            return True
        now = timezone.now()
        entitlements = list(
            TenantEntitlement.objects.select_for_update().filter(
                feature_code=feature_code,
                feature_type=FeatureType.USAGE,
                status=TenantEntitlement.Status.ACTIVE,
            ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).filter(
                quantity_used__lt=F("quantity_granted")
            ).order_by("activated_at", "created_at")
        )
        total_remaining = sum(entitlement.quantity_remaining for entitlement in entitlements)
        if total_remaining < amount:
            return False

        remaining_to_consume = amount
        for entitlement in entitlements:
            if remaining_to_consume <= 0:
                break
            available = entitlement.quantity_remaining
            if available <= 0:
                continue
            consumed = min(available, remaining_to_consume)
            TenantEntitlement.objects.filter(pk=entitlement.pk).update(quantity_used=F("quantity_used") + consumed)
            UsageRecord.objects.create(
                entitlement=entitlement,
                feature_code=feature_code,
                quantity_used=consumed,
                description=description,
                metadata={**(metadata or {}), "requested_amount": amount},
            )
            if consumed == available:
                TenantEntitlement.objects.filter(pk=entitlement.pk).update(
                    status=TenantEntitlement.Status.EXHAUSTED,
                    updated_at=timezone.now(),
                )
            remaining_to_consume -= consumed

        self.invalidate_cache(feature_code)
        return True


def get_engine_for_request(request) -> FeatureEntitlementEngine:
    return FeatureEntitlementEngine(getattr(getattr(request, "tenant", None), "schema_name", None))


def enforce_quota(feature_code: str, requested: int = 1, engine: FeatureEntitlementEngine | None = None):
    engine = engine or FeatureEntitlementEngine()
    quota = engine.rebuild_quota(feature_code)
    if requested > 0 and quota.used_quota + requested > quota.total_quota:
        raise QuotaExceededError(f"{feature_code.replace('_', ' ').title()} quota exceeded.")
    return quota


def require_usage_balance(feature_code: str, amount: int = 1, engine: FeatureEntitlementEngine | None = None):
    engine = engine or FeatureEntitlementEngine()
    if engine.get_usage_remaining(feature_code) < amount:
        raise UsageBalanceError(f"Not enough {feature_code.replace('_', ' ')} remaining.")
    return True


def require_feature(feature_code: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            engine = get_engine_for_request(request)
            if engine.has_feature(feature_code):
                return view_func(request, *args, **kwargs)
            prefix = kwargs.get("prefix")
            if not prefix and args:
                first_arg = args[0]
                if isinstance(first_arg, str):
                    prefix = first_arg
            if prefix:
                messages.error(request, f"{feature_code.replace('_', ' ').title()} is not enabled for this store.")
                return redirect("dashboard:feature_marketplace:catalog", prefix=prefix)
            raise FeatureAccessError(f"Missing feature: {feature_code}")

        return wrapped

    return decorator
