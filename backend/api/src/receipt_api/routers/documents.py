"""Document endpoints (Phase 4: upload URL issuance)."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import PurePath

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from receipt_api.auth import CurrentUserDep
from receipt_api.deps import RepositoryDep, SettingsDep, StorageDep
from receipt_shared.files import EXTENSION_MIME, SUPPORTED_MIME_TYPES, normalize_mime
from receipt_shared.models.enums import DocumentStatus
from receipt_shared.repository import DocumentRecord
from receipt_shared.storage import upload_object_name

logger = logging.getLogger("receipt.api.documents")
router = APIRouter(prefix="/documents", tags=["documents"])

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255, examples=["receipt.pdf"])
    content_type: str = Field(
        min_length=1, max_length=100, examples=["application/pdf"],
        description="application/pdf, image/png or image/jpeg",
    )  # fmt: skip
    size_bytes: int = Field(gt=0, description="Exact size of the file that will be uploaded")
    sha256: str | None = Field(
        default=None,
        description="Optional hex SHA-256 of the file; the worker verifies it after upload.",
    )

    @field_validator("sha256")
    @classmethod
    def _check_sha(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256_RE.match(value):
            raise ValueError("must be a 64-character hex SHA-256 digest")
        return value.lower() if value else None


class UploadUrlResponse(BaseModel):
    document_id: str
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str] = Field(
        description="Headers the upload request must send exactly as given"
    )
    expires_at: datetime
    status: DocumentStatus


@router.post(
    "/upload-url",
    response_model=UploadUrlResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a document and get a short-lived URL to upload its file",
    responses={
        401: {"description": "Not signed in"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported file type"},
    },
)
def create_upload_url(
    body: UploadUrlRequest,
    user: CurrentUserDep,
    settings: SettingsDep,
    storage: StorageDep,
    repository: RepositoryDep,
) -> UploadUrlResponse:
    content_type = normalize_mime(body.content_type)
    ext = PurePath(body.filename).suffix.lower()
    if content_type not in SUPPORTED_MIME_TYPES or ext not in EXTENSION_MIME:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Unsupported file type. Upload a PDF, PNG or JPEG (.pdf, .png, .jpg, .jpeg).",
        )
    if EXTENSION_MIME[ext] != content_type:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"The file extension '{ext}' does not match the content type '{content_type}'.",
        )
    if body.size_bytes > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File is too large. The limit is {settings.max_upload_bytes // (1024 * 1024)} MB.",
        )

    document_id = uuid.uuid4().hex
    object_name = upload_object_name(user.uid, document_id, body.filename)
    signed = storage.upload_url(object_name, content_type=content_type, size_bytes=body.size_bytes)
    record = DocumentRecord(
        document_id=document_id,
        user_id=user.uid,
        status=DocumentStatus.AWAITING_UPLOAD,
        original_filename=body.filename,
        bucket=storage.bucket_name,
        object_name=object_name,
        content_type=content_type,
        size_bytes=body.size_bytes,
        client_sha256=body.sha256,
        upload_url_expires_at=signed.expires_at,
    )
    repository.create(record)
    logger.info(
        "upload url issued",
        extra={
            "document_id": document_id,
            "content_type": content_type,
            "size_bytes": body.size_bytes,
        },
    )
    return UploadUrlResponse(
        document_id=document_id,
        upload_url=signed.url,
        method=signed.method,
        headers=signed.headers,
        expires_at=signed.expires_at,
        status=record.status,
    )
