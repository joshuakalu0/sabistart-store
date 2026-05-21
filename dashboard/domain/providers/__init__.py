from dashboard.domain.providers.base import (
    DomainAvailabilityResult,
    DomainContactPayload,
    DomainMutationResult,
    DomainProviderAdapter,
    ProviderDnsRecord,
)
from dashboard.domain.providers.registry import get_provider_adapter

__all__ = [
    "DomainAvailabilityResult",
    "DomainContactPayload",
    "DomainMutationResult",
    "DomainProviderAdapter",
    "ProviderDnsRecord",
    "get_provider_adapter",
]
