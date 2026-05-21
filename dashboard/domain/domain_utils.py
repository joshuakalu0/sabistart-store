from __future__ import annotations

import re


def normalize_domain_name(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.rstrip("/")
    return value


def split_registered_domain(domain_name: str, known_tlds: list[str] | None = None) -> tuple[str, str]:
    domain_name = normalize_domain_name(domain_name)
    labels = [label for label in domain_name.split(".") if label]
    if len(labels) < 2:
        return domain_name, ""

    known_tlds = sorted({(item or "").lstrip(".").lower() for item in (known_tlds or []) if item}, key=len, reverse=True)
    for tld in known_tlds:
        suffix = f".{tld}"
        if domain_name.endswith(suffix) and len(labels) > len(tld.split(".")):
            sld = domain_name[: -len(suffix)]
            return sld, tld

    return ".".join(labels[:-1]), labels[-1]
