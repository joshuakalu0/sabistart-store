from __future__ import annotations

from decimal import Decimal
from typing import Iterable
from xml.etree import ElementTree as ET

import requests
from django.utils import timezone

from dashboard.domain.commerce_models import TldCatalogEntry
from dashboard.domain.domain_utils import split_registered_domain
from dashboard.domain.providers.base import (
    DomainAvailabilityResult,
    DomainContactPayload,
    DomainMutationResult,
    DomainProviderAdapter,
    ProviderDnsRecord,
)


def _local_name(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


class NamecheapAdapter(DomainProviderAdapter):
    provider_code = "namecheap"

    def _tlds(self) -> list[str]:
        return list(
            TldCatalogEntry.objects.filter(provider__code=self.provider_code)
            .values_list("tld", flat=True)
        )

    def _api_params(self, command: str, extra: dict | None = None) -> dict:
        params = {
            "ApiUser": self.credential.api_user or self.credential.username,
            "ApiKey": self.credential.api_key,
            "UserName": self.credential.username,
            "ClientIp": self.credential.client_ip,
            "Command": command,
        }
        params.update(extra or {})
        return params

    def _api_call(self, command: str, extra: dict | None = None) -> ET.Element:
        response = requests.get(
            self.credential.endpoint,
            params=self._api_params(command, extra),
            timeout=self.credential.request_timeout_seconds or 20,
        )
        response.raise_for_status()
        xml_root = ET.fromstring(response.text)
        if xml_root.attrib.get("Status", "").upper() == "ERROR":
            errors = []
            for node in xml_root.iter():
                if _local_name(node) == "Error":
                    errors.append((node.text or "").strip())
            raise ValueError("; ".join(errors) or "Namecheap request failed.")
        return xml_root

    def _contact_params(self, prefix: str, contact: DomainContactPayload) -> dict:
        phone = contact.phone if contact.phone.startswith("+") else f"+{contact.phone}"
        return {
            f"{prefix}FirstName": contact.first_name,
            f"{prefix}LastName": contact.last_name,
            f"{prefix}OrganizationName": contact.organization or contact.first_name,
            f"{prefix}JobTitle": "Owner",
            f"{prefix}Address1": contact.address1,
            f"{prefix}Address2": contact.address2,
            f"{prefix}City": contact.city,
            f"{prefix}StateProvince": contact.state_province,
            f"{prefix}PostalCode": contact.postal_code,
            f"{prefix}Country": contact.country_code,
            f"{prefix}Phone": phone,
            f"{prefix}EmailAddress": contact.email,
        }

    def _pricing_for(self, domain_name: str) -> tuple[Decimal, Decimal, str]:
        _, tld = split_registered_domain(domain_name, self._tlds())
        entry = TldCatalogEntry.objects.filter(provider__code=self.provider_code, tld__iexact=f".{tld}".rstrip(".")).first()
        if entry is None:
            entry = TldCatalogEntry.objects.filter(provider__code=self.provider_code, tld__iexact=f".{tld}").first()
        if entry is None:
            return Decimal("0.00"), Decimal("0.00"), "USD"
        return entry.selling_registration_price, entry.selling_renewal_price, entry.currency

    def check_availability(self, domains: list[str]) -> list[DomainAvailabilityResult]:
        if not domains:
            return []
        xml_root = self._api_call("namecheap.domains.check", {"DomainList": ",".join(domains)})
        results: list[DomainAvailabilityResult] = []
        for node in xml_root.iter():
            if _local_name(node) != "DomainCheckResult":
                continue
            domain_name = node.attrib.get("Domain", "").lower()
            reg_price, renewal_price, currency = self._pricing_for(domain_name)
            results.append(
                DomainAvailabilityResult(
                    domain_name=domain_name,
                    is_available=node.attrib.get("Available", "").lower() == "true",
                    is_supported=node.attrib.get("ErrorNo", "") in {"", "0"},
                    is_premium=node.attrib.get("IsPremiumName", "").lower() == "true",
                    currency=currency,
                    registration_price=reg_price,
                    renewal_price=renewal_price,
                    status_reason=node.attrib.get("Description", ""),
                    raw_payload=node.attrib,
                )
            )
        return results

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
        params = {
            "DomainName": domain_name,
            "Years": years,
            "AddFreeWhoisguard": "yes" if privacy_enabled else "no",
            "WGEnabled": "yes" if privacy_enabled else "no",
        }
        for prefix in ("Registrant", "Tech", "Admin", "AuxBilling"):
            params.update(self._contact_params(prefix, contact))

        if nameserver_mode == "custom" and custom_nameservers:
            params["Nameservers"] = ",".join(custom_nameservers)

        xml_root = self._api_call("namecheap.domains.create", params)
        domain_node = next((node for node in xml_root.iter() if _local_name(node) == "DomainCreateResult"), None)
        expires_at = None
        if domain_node is not None and domain_node.attrib.get("ChargedAmount"):
            try:
                expires_at = timezone.now() + timezone.timedelta(days=365 * int(years))
            except Exception:
                expires_at = None
        return DomainMutationResult(
            success=True,
            message="Domain registered successfully.",
            domain_name=domain_name,
            provider_domain_id=domain_name,
            provider_order_id=(domain_node.attrib.get("OrderID", "") if domain_node is not None else ""),
            provider_status="active",
            current_nameservers=custom_nameservers,
            expires_at=expires_at,
            raw_payload={"attributes": dict(domain_node.attrib) if domain_node is not None else {}},
        )

    def renew_domain(self, *, domain_name: str, years: int) -> DomainMutationResult:
        info = self.get_domain_info(domain_name)
        expiry_year = str(info.expires_at.year if info.expires_at else timezone.now().year)
        xml_root = self._api_call(
            "namecheap.domains.renew",
            {"DomainName": domain_name, "Years": years, "ExpYear": expiry_year},
        )
        renew_node = next((node for node in xml_root.iter() if _local_name(node) == "DomainRenewResult"), None)
        return DomainMutationResult(
            success=True,
            message="Domain renewed successfully.",
            domain_name=domain_name,
            provider_domain_id=domain_name,
            provider_order_id=(renew_node.attrib.get("OrderID", "") if renew_node is not None else ""),
            provider_status="active",
            expires_at=(info.expires_at + timezone.timedelta(days=365 * years) if info.expires_at else None),
            raw_payload={"attributes": dict(renew_node.attrib) if renew_node is not None else {}},
        )

    def get_domain_info(self, domain_name: str) -> DomainMutationResult:
        xml_root = self._api_call("namecheap.domains.getInfo", {"DomainName": domain_name})
        info_node = next((node for node in xml_root.iter() if _local_name(node) == "DomainGetInfoResult"), None)
        expires_at = None
        status = ""
        nameservers: list[str] = []
        if info_node is not None:
            status = info_node.attrib.get("Status", "")
            for node in info_node.iter():
                local = _local_name(node)
                if local == "DomainDetails":
                    exp = node.attrib.get("ExpiredDate") or node.attrib.get("CreatedDate")
                    if exp:
                        try:
                            expires_at = timezone.datetime.fromisoformat(exp.replace("Z", "+00:00"))
                        except Exception:
                            expires_at = None
                if local == "Nameserver":
                    value = (node.text or "").strip()
                    if value:
                        nameservers.append(value)
        return DomainMutationResult(
            success=True,
            message="Domain info fetched.",
            domain_name=domain_name,
            provider_domain_id=domain_name,
            provider_status=status,
            current_nameservers=nameservers,
            expires_at=expires_at,
            raw_payload={"attributes": dict(info_node.attrib) if info_node is not None else {}},
        )

    def get_nameservers(self, domain_name: str) -> DomainMutationResult:
        info = self.get_domain_info(domain_name)
        return DomainMutationResult(
            success=True,
            message="Nameservers fetched.",
            domain_name=domain_name,
            current_nameservers=info.current_nameservers,
            provider_status=info.provider_status,
            expires_at=info.expires_at,
            raw_payload=info.raw_payload,
        )

    def set_nameservers(self, *, domain_name: str, nameservers: list[str]) -> DomainMutationResult:
        sld, tld = split_registered_domain(domain_name, self._tlds())
        command = "namecheap.domains.dns.setDefault"
        params: dict = {"SLD": sld, "TLD": tld}
        if nameservers:
            command = "namecheap.domains.dns.setCustom"
            params["Nameservers"] = ",".join(nameservers)
        self._api_call(command, params)
        return DomainMutationResult(
            success=True,
            message="Nameservers updated.",
            domain_name=domain_name,
            current_nameservers=nameservers,
            provider_status="updated",
            raw_payload={"command": command},
        )

    def get_dns_records(self, domain_name: str) -> DomainMutationResult:
        sld, tld = split_registered_domain(domain_name, self._tlds())
        xml_root = self._api_call("namecheap.domains.dns.getHosts", {"SLD": sld, "TLD": tld})
        records: list[ProviderDnsRecord] = []
        for node in xml_root.iter():
            if _local_name(node) != "host":
                continue
            records.append(
                ProviderDnsRecord(
                    host=node.attrib.get("Name", ""),
                    record_type=node.attrib.get("Type", ""),
                    value=node.attrib.get("Address", ""),
                    ttl=int(node.attrib.get("TTL", "1800") or 1800),
                    priority=int(node.attrib.get("MXPref", "10") or 10),
                    provider_record_id=node.attrib.get("HostId", ""),
                )
            )
        return DomainMutationResult(
            success=True,
            message="DNS records fetched.",
            domain_name=domain_name,
            dns_records=records,
            raw_payload={"count": len(records)},
        )

    def set_dns_records(self, *, domain_name: str, records: list[ProviderDnsRecord]) -> DomainMutationResult:
        sld, tld = split_registered_domain(domain_name, self._tlds())
        params: dict[str, str | int] = {"SLD": sld, "TLD": tld}
        for idx, record in enumerate(records, start=1):
            params[f"HostName{idx}"] = record.host
            params[f"RecordType{idx}"] = record.record_type
            params[f"Address{idx}"] = record.value
            params[f"TTL{idx}"] = record.ttl
            params[f"MXPref{idx}"] = record.priority
        self._api_call("namecheap.domains.dns.setHosts", params)
        return DomainMutationResult(
            success=True,
            message="DNS records updated.",
            domain_name=domain_name,
            dns_records=records,
            raw_payload={"count": len(records)},
        )

    def get_tld_catalog(self) -> list[dict]:
        xml_root = self._api_call("namecheap.domains.getTldList")
        rows: list[dict] = []
        for node in xml_root.iter():
            if _local_name(node) != "Tld":
                continue
            name = node.attrib.get("Name", "")
            if not name:
                continue
            rows.append(
                {
                    "tld": f".{name.lstrip('.')}",
                    "supports_registration": node.attrib.get("IsApiRegisterable", "true").lower() == "true",
                    "supports_renewal": True,
                    "supports_dns": True,
                    "raw_payload": dict(node.attrib),
                }
            )
        return rows
