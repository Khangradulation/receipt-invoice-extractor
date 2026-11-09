"""Google Cloud Storage operations for documents.

Signed URLs are V4 and signed through the IAM ``signBlob`` API as ``SIGNING_SERVICE_ACCOUNT``
(no private keys anywhere): on Cloud Run with the service's own identity, locally with the
developer's credentials, which need Token Creator on that service account.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import google.auth
import google.cloud.storage as storage
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request

from receipt_shared.config import Settings

logger = logging.getLogger("receipt.storage")

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class StorageNotConfiguredError(RuntimeError):
    pass


class ObjectTooLargeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SignedUrl:
    url: str
    method: str
    expires_at: datetime
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StoredObject:
    data: bytes
    bucket: str
    name: str
    generation: int
    size: int
    content_type: str | None
    metadata: dict[str, str]

    @property
    def gcs_uri(self) -> str:
        return f"gs://{self.bucket}/{self.name}"


class DocumentStorage:
    def __init__(
        self,
        settings: Settings,
        *,
        client: storage.Client | None = None,
        credentials: Credentials | None = None,
    ) -> None:
        if not settings.gcs_upload_bucket:
            raise StorageNotConfiguredError("GCS_UPLOAD_BUCKET is not set")
        self._settings = settings
        self.bucket_name = settings.gcs_upload_bucket
        if credentials is None:
            credentials, _ = google.auth.default(scopes=_SCOPES)
        self._credentials = credentials
        self._client = client or storage.Client(
            project=settings.gcp_project_id, credentials=credentials
        )
        self._bucket = self._client.bucket(self.bucket_name)
        self._lock = threading.Lock()

    # -- signing ------------------------------------------------------------------------------
    def _signing_args(self) -> dict[str, Any]:
        sa = self._settings.signing_service_account
        if not sa:
            raise StorageNotConfiguredError("SIGNING_SERVICE_ACCOUNT is not set")
        with self._lock:
            if not self._credentials.valid:
                self._credentials.refresh(Request())  # type: ignore[no-untyped-call]
            token = self._credentials.token
        return {"service_account_email": sa, "access_token": token}

    def upload_url(self, object_name: str, *, content_type: str, size_bytes: int) -> SignedUrl:
        """A PUT URL that only accepts exactly ``size_bytes`` bytes of ``content_type``."""
        ttl = timedelta(seconds=self._settings.signed_url_ttl_seconds)
        headers = {"x-goog-content-length-range": f"{size_bytes},{size_bytes}"}
        url = self._bucket.blob(object_name).generate_signed_url(
            version="v4",
            expiration=ttl,
            method="PUT",
            content_type=content_type,
            headers=headers,
            **self._signing_args(),
        )
        return SignedUrl(
            url=url,
            method="PUT",
            expires_at=datetime.now(UTC) + ttl,
            headers={"Content-Type": content_type, **headers},
        )

    def download_url(self, object_name: str, *, filename: str | None = None) -> SignedUrl:
        """A short-lived GET URL for viewing a stored document inline."""
        ttl = timedelta(seconds=self._settings.signed_url_ttl_seconds)
        disposition = f'inline; filename="{filename}"' if filename else "inline"
        url = self._bucket.blob(object_name).generate_signed_url(
            version="v4",
            expiration=ttl,
            method="GET",
            response_disposition=disposition,
            **self._signing_args(),
        )
        return SignedUrl(url=url, method="GET", expires_at=datetime.now(UTC) + ttl)

    # -- objects ------------------------------------------------------------------------------
    def read(self, object_name: str, *, generation: int | None = None) -> StoredObject:
        """Download an object, refusing anything larger than MAX_UPLOAD_BYTES."""
        blob = self._bucket.get_blob(object_name, generation=generation)
        if blob is None:
            raise FileNotFoundError(f"gs://{self.bucket_name}/{object_name}")
        size = int(blob.size or 0)
        if size > self._settings.max_upload_bytes:
            raise ObjectTooLargeError(f"object is {size} bytes")
        # get_blob() pinned the generation; the download is verified against its CRC32C.
        data = blob.download_as_bytes(checksum="crc32c")
        return StoredObject(
            data=data,
            bucket=self.bucket_name,
            name=object_name,
            generation=int(blob.generation or 0),
            size=size,
            content_type=blob.content_type,
            metadata=dict(blob.metadata or {}),
        )

    def exists(self, object_name: str) -> bool:
        return bool(self._bucket.blob(object_name).exists())
