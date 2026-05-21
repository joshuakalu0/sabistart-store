from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ProviderDnsRecord:
    host: str
    record_type: str
    value: str
    ttl: int = 1800
    priority: int = 10
    provider_record_id: str = ""


@dataclass
class DomainAvailabilityResult:
    domain_name: str
    is_available: bool
    is_supported: bool = True
    is_premium: bool = False
    currency: str = "USD"
    registration_price: Decimal = Decimal("0.00")
    renewal_price: Decimal = Decimal("0.00")
    status_reason: str = ""
    suggestion_score: Decimal = Decimal("0.00")
    raw_payload: dict = field(default_factory=dict)


@dataclass
class DomainMutationResult:
    success: bool
    message: str = ""
    domain_name: str = ""
    provider_domain_id: str = ""
    provider_order_id: str = ""
    provider_status: str = ""
    current_nameservers: list[str] = field(default_factory=list)
    dns_records: list[ProviderDnsRecord] = field(default_factory=list)
    expires_at: object | None = None
    raw_payload: dict = field(default_factory=dict)


@dataclass
class DomainContactPayload:
    first_name: str
    last_name: str
    organization: str
    email: str
    phone: str
    address1: str
    address2: str
    city: str
    state_province: str
    postal_code: str
    country_code: str


class DomainProviderAdapter(ABC):
    provider_code: str = ""

    def __init__(self, credential):
        self.credential = credential

    @abstractmethod
    def check_availability(self, domains: list[str]) -> list[DomainAvailabilityResult]:
        raise NotImplementedError

    @abstractmethod
    def register_domain(
        self,
        *,
        domain_name: str,
        years: int,
        contact: DomainContactPayload,
        privacy_enabled: bool,
        nameserver_mode: str,
        custom_nameservers: list[str],
    ) -> DomainMutationResult:
        raise NotImplementedError

    @abstractmethod
    def renew_domain(self, *, domain_name: str, years: int) -> DomainMutationResult:
        raise NotImplementedError

    @abstractmethod
    def get_domain_info(self, domain_name: str) -> DomainMutationResult:
        raise NotImplementedError

    @abstractmethod
    def get_nameservers(self, domain_name: str) -> DomainMutationResult:
        raise NotImplementedError

    @abstractmethod
    def set_nameservers(self, *, domain_name: str, nameservers: list[str]) -> DomainMutationResult:
        raise NotImplementedError

    @abstractmethod
    def get_dns_records(self, domain_name: str) -> DomainMutationResult:
        raise NotImplementedError

    @abstractmethod
    def set_dns_records(self, *, domain_name: str, records: list[ProviderDnsRecord]) -> DomainMutationResult:
        raise NotImplementedError

    def get_tld_catalog(self) -> list[dict]:
        return []
