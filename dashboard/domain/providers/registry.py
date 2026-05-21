from __future__ import annotations

from dashboard.domain.providers.base import DomainProviderAdapter
from dashboard.domain.providers.namecheap import NamecheapAdapter


PROVIDER_ADAPTERS: dict[str, type[DomainProviderAdapter]] = {
    "namecheap": NamecheapAdapter,
}


def get_provider_adapter(code: str):
    return PROVIDER_ADAPTERS.get((code or "").strip().lower())
