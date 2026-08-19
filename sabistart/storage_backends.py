from __future__ import annotations

import mimetypes
import os
import posixpath
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.db import connection
from django.utils.deconstruct import deconstructible
from django.utils.encoding import filepath_to_uri

from django_tenants import utils as tenant_utils

try:
    from vercel.blob import delete as delete_blob
    from vercel.blob import get as get_blob
    from vercel.blob import head as head_blob
    from vercel.blob import list_objects
    from vercel.blob import put as put_blob
except Exception as exc:  # pragma: no cover - dependency availability
    delete_blob = get_blob = head_blob = list_objects = put_blob = None
    VERCEL_BLOB_IMPORT_ERROR = exc
else:  # pragma: no cover - trivial
    VERCEL_BLOB_IMPORT_ERROR = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _blob_result_value(blob: Any, key: str, default=None):
    if blob is None:
        return default
    if isinstance(blob, dict):
        return blob.get(key, default)
    return getattr(blob, key, default)


def _is_missing_blob_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 404:
        return True

    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 404:
        return True

    message = str(exc).lower()
    return "404" in message or "not found" in message or "blobnotfound" in message


def _join_url(base: str, name: str) -> str:
    clean_base = base.rstrip("/") + "/"
    clean_name = filepath_to_uri(name).lstrip("/")
    return clean_base + clean_name


@dataclass
class BlobOpenPayload:
    content: bytes
    content_type: str | None = None
    content_disposition: str | None = None
    etag: str | None = None
    uploaded_at: datetime | None = None
    size: int | None = None


@deconstructible
class VercelBlobStorage(Storage):
    """
    Persist tenant media in Vercel Blob while keeping Django media URLs stable.

    The blob store is used as the durable backend, but media is delivered through
    the Django app so templates and existing `field.url` usage continue to work.
    """

    def __init__(self):
        if VERCEL_BLOB_IMPORT_ERROR is not None:
            raise ImproperlyConfigured(
                "Install the `vercel` package to use sabistart.storage_backends.VercelBlobStorage."
            ) from VERCEL_BLOB_IMPORT_ERROR
        self.token = os.getenv("BLOB_READ_WRITE_TOKEN")
        self.access = os.getenv("VERCEL_BLOB_ACCESS", "private").strip().lower() or "private"
        self.cache_control_max_age = int(os.getenv("VERCEL_BLOB_CACHE_MAX_AGE", "31536000"))
        self.allow_overwrite = _env_bool("VERCEL_BLOB_ALLOW_OVERWRITE", default=True)

    @property
    def relative_media_root(self) -> str:
        return getattr(settings, "MULTITENANT_RELATIVE_MEDIA_ROOT", "%s")

    @property
    def relative_media_url(self) -> str:
        multitenant_relative_url = getattr(settings, "MULTITENANT_RELATIVE_MEDIA_ROOT", "%s")
        joined = "/".join(s.strip("/") for s in [settings.MEDIA_URL, multitenant_relative_url]) + "/"
        if not joined.startswith("/"):
            joined = "/" + joined
        return joined

    @property
    def tenant_prefix(self) -> str:
        return tenant_utils.parse_tenant_config_path(self.relative_media_root).replace("\\", "/").strip("/")

    @property
    def base_url(self) -> str:
        return tenant_utils.parse_tenant_config_path(self.relative_media_url)

    def _normalize_name(self, name: str) -> str:
        if not name:
            return ""
        normalized = str(name).replace("\\", "/").strip("/")
        return posixpath.normpath(normalized).replace("\\", "/").lstrip("/")

    def _blob_path(self, name: str) -> str:
        logical_name = self.strip_tenant_prefix(name)
        if not logical_name:
            return self.tenant_prefix
        return f"{self.tenant_prefix}/{logical_name}".strip("/")

    def strip_tenant_prefix(self, name: str) -> str:
        normalized = self._normalize_name(name)
        tenant_prefix = self.tenant_prefix
        if normalized.startswith(f"{tenant_prefix}/"):
            return normalized[len(tenant_prefix) + 1 :]
        if normalized == tenant_prefix:
            return ""
        return normalized

    def get_available_name(self, name, max_length=None):
        normalized = self._normalize_name(name)
        if self.allow_overwrite:
            return normalized
        return super().get_available_name(normalized, max_length=max_length)

    def _save(self, name, content):
        logical_name = self.get_available_name(name)
        blob_path = self._blob_path(logical_name)
        content_type = getattr(content, "content_type", None) or mimetypes.guess_type(logical_name)[0] or "application/octet-stream"
        payload = content.read()

        put_blob(
            blob_path,
            payload,
            access=self.access,
            token=self.token,
            overwrite=self.allow_overwrite,
            add_random_suffix=False,
            cache_control_max_age=self.cache_control_max_age,
            content_type=content_type,
        )
        return logical_name

    def delete(self, name):
        logical_name = self.strip_tenant_prefix(name)
        if not logical_name:
            return
        try:
            delete_blob(self._blob_path(logical_name), token=self.token)
        except Exception as exc:  # pragma: no cover - remote behavior
            if not _is_missing_blob_error(exc):
                raise

    def exists(self, name):
        logical_name = self.strip_tenant_prefix(name)
        if not logical_name:
            return False
        try:
            head_blob(self._blob_path(logical_name), token=self.token)
            return True
        except Exception as exc:  # pragma: no cover - remote behavior
            if _is_missing_blob_error(exc):
                return False
            raise

    def _head(self, name):
        logical_name = self.strip_tenant_prefix(name)
        if not logical_name:
            return None
        return head_blob(self._blob_path(logical_name), token=self.token)

    def _open_payload(self, name, if_none_match: str | None = None) -> BlobOpenPayload | None:
        logical_name = self.strip_tenant_prefix(name)
        if not logical_name:
            return None

        result = get_blob(
            self._blob_path(logical_name),
            access=self.access,
            token=self.token,
            if_none_match=if_none_match,
        )
        if result is None:
            return None

        status_code = getattr(result, "status_code", None)
        if status_code == 304:
            return BlobOpenPayload(content=b"", etag=if_none_match)

        content = _blob_result_value(result, "content", b"")
        return BlobOpenPayload(
            content=content,
            content_type=_blob_result_value(result, "content_type"),
            content_disposition=_blob_result_value(result, "content_disposition"),
            etag=_blob_result_value(result, "etag"),
            uploaded_at=_blob_result_value(result, "uploaded_at"),
            size=_blob_result_value(result, "size"),
        )

    def _open(self, name, mode="rb"):
        payload = self._open_payload(name)
        if payload is None:
            raise FileNotFoundError(name)
        file_object = ContentFile(payload.content, name=self.strip_tenant_prefix(name))
        file_object.content_type = payload.content_type
        file_object.etag = payload.etag
        file_object.uploaded_at = payload.uploaded_at
        file_object.size = payload.size if payload.size is not None else len(payload.content)
        return file_object

    def size(self, name):
        metadata = self._head(name)
        if metadata is None:
            raise FileNotFoundError(name)
        return _blob_result_value(metadata, "size", 0)

    def url(self, name):
        logical_name = self.strip_tenant_prefix(name)
        return _join_url(self.base_url, logical_name)

    def get_modified_time(self, name):
        metadata = self._head(name)
        if metadata is None:
            raise FileNotFoundError(name)
        return _blob_result_value(metadata, "uploaded_at")

    def listdir(self, path):
        logical_path = self.strip_tenant_prefix(path)
        prefix = self._blob_path(logical_path).rstrip("/")
        if prefix:
            prefix = f"{prefix}/"

        directories = set()
        files = []
        try:
            response = list_objects(token=self.token, prefix=prefix or f"{self.tenant_prefix}/", limit=1000)
        except Exception:  # pragma: no cover - remote behavior
            return [], []

        blobs = _blob_result_value(response, "blobs", []) or []
        for blob in blobs:
            pathname = _blob_result_value(blob, "pathname", "")
            if not pathname:
                continue
            tenant_relative = self.strip_tenant_prefix(pathname)
            if logical_path:
                tenant_relative = tenant_relative[len(logical_path.strip("/") + "/") :] if tenant_relative.startswith(logical_path.strip("/") + "/") else tenant_relative
            first_segment, _, remainder = tenant_relative.partition("/")
            if remainder:
                directories.add(first_segment)
            elif first_segment:
                files.append(first_segment)

        return sorted(directories), sorted(files)

    def path(self, name):
        raise NotImplementedError("Vercel Blob storage does not expose filesystem paths.")
