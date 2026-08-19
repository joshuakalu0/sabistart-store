from __future__ import annotations

from urllib.parse import quote

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotModified

from sabistart.storage_backends import VercelBlobStorage


def media_proxy(request, path: str):
    storage = default_storage
    if not isinstance(storage, VercelBlobStorage):
        raise Http404("Media proxy is only available for Vercel Blob storage.")

    logical_name = storage.strip_tenant_prefix(path)
    if not logical_name:
        raise Http404("Invalid media path.")

    try:
        payload = storage._open_payload(logical_name, if_none_match=request.headers.get("If-None-Match"))
    except Exception as exc:  # pragma: no cover - remote behavior
        if "304" in str(exc):
            return HttpResponseNotModified()
        raise Http404("Media file not found.") from exc

    if payload is None:
        raise Http404("Media file not found.")
    if payload.etag and payload.content == b"" and request.headers.get("If-None-Match") == payload.etag:
        return HttpResponseNotModified()

    file_object = ContentFile(payload.content, name=logical_name.rsplit("/", 1)[-1])
    response = FileResponse(
        file_object,
        content_type=payload.content_type or "application/octet-stream",
    )
    if payload.size is not None:
        response["Content-Length"] = str(payload.size)
    if payload.etag:
        response["ETag"] = payload.etag
    if payload.uploaded_at:
        response["Last-Modified"] = payload.uploaded_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
    if payload.content_disposition:
        response["Content-Disposition"] = payload.content_disposition
    else:
        filename = logical_name.rsplit("/", 1)[-1]
        response["Content-Disposition"] = f'inline; filename="{quote(filename)}"'
    response["Cache-Control"] = f"public, max-age={storage.cache_control_max_age}"
    return response
