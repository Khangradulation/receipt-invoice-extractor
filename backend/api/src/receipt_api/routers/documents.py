"""Document endpoints: upload URL, listing, details, status, extraction, file URL, delete."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from receipt_api.auth import CurrentUser
from receipt_api.deletion import DocumentBusyError, delete_document
from receipt_api.deps import (
    AnalyticsWriterDep,
    RepositoryDep,
    ReviewServiceDep,
    SettingsDep,
    StorageDep,
)
from receipt_api.ownership import owned_record
from receipt_api.ratelimit import rate_limit
from receipt_api.review_service import ReviewService
from receipt_api.schemas import (
    Correction,
    DocumentDetail,
    DocumentPage,
    DocumentStatusResponse,
    ExtractionResponse,
    FileUrlResponse,
    HistoryEntry,
    ReviewDecision,
    ReviewSummary,
    status_response,
    summary,
)
from receipt_shared.files import EXTENSION_MIME, SUPPORTED_MIME_TYPES, normalize_mime
from receipt_shared.models.enums import DocumentStatus
from receipt_shared.models.extraction import ExtractionResult
from receipt_shared.repository import DocumentRecord, InvalidCursorError
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
    user: Annotated[CurrentUser, Depends(rate_limit("upload"))],
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


ReadUser = Annotated[CurrentUser, Depends(rate_limit("read"))]


def detail(record: DocumentRecord, service: ReviewService) -> DocumentDetail:
    state = service.state(record)
    effective = state.corrected or state.original
    base = summary(record, effective).model_dump()
    return DocumentDetail(
        **base,
        size_bytes=record.size_bytes,
        page_count=record.page_count,
        processing_attempts=record.processing_attempts,
        model_version=record.model_version,
        uploaded_at=record.uploaded_at,
        processing_started_at=record.processing_started_at,
        extracted_at=record.extracted_at,
        processing_duration_ms=record.processing_duration_ms,
        extraction=state.original,
        corrected=state.corrected,
        validation=state.validation,
        history=[HistoryEntry.model_validate(h) for h in record.history],
        review=review_summary(record, state.corrections),
    )


def review_summary(
    record: DocumentRecord, corrections: list[dict[str, object]]
) -> ReviewSummary | None:
    extra = record.model_extra or {}
    decision = None
    if record.status is DocumentStatus.APPROVED and extra.get("approved_at"):
        decision = ReviewDecision(
            action="APPROVED", by=str(extra.get("approved_by")), at=extra["approved_at"]
        )
    elif record.status is DocumentStatus.REJECTED and extra.get("rejected_at"):
        decision = ReviewDecision(
            action="REJECTED",
            by=str(extra.get("rejected_by")),
            at=extra["rejected_at"],
            reason=extra.get("rejection_reason"),
        )
    items = [Correction.model_validate(c) for c in corrections if c.get("action") == "CORRECTION"]
    if decision is None and not items:
        return None
    return ReviewSummary(decision=decision, corrections=items)


@router.get("", response_model=DocumentPage, summary="List your documents (newest first)")
def list_documents(
    user: ReadUser,
    repository: RepositoryDep,
    service: ReviewServiceDep,
    status_filter: Annotated[
        list[DocumentStatus] | None, Query(alias="status", description="Filter by status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> DocumentPage:
    try:
        page = repository.list_for_user(
            user.uid, statuses=status_filter, limit=limit, cursor=cursor
        )
    except InvalidCursorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid page cursor.") from exc
    return DocumentPage(
        items=[summary(r, service.effective(r)) for r in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{document_id}", response_model=DocumentDetail, summary="Document details")
def get_document(
    document_id: str, user: ReadUser, repository: RepositoryDep, service: ReviewServiceDep
) -> DocumentDetail:
    return detail(owned_record(repository, document_id, user), service)


@router.get(
    "/{document_id}/status", response_model=DocumentStatusResponse, summary="Processing status"
)
def get_status(
    document_id: str, user: ReadUser, repository: RepositoryDep
) -> DocumentStatusResponse:
    return status_response(owned_record(repository, document_id, user))


@router.get(
    "/{document_id}/extraction",
    response_model=ExtractionResponse,
    summary="Original Gemini extraction",
    responses={404: {"description": "Not found or not extracted yet"}},
)
def get_extraction(
    document_id: str, user: ReadUser, repository: RepositoryDep
) -> ExtractionResponse:
    record = owned_record(repository, document_id, user)
    if record.extraction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document has not been extracted yet.")
    result = ExtractionResult.model_validate(record.extraction)
    return ExtractionResponse(
        document_id=record.document_id,
        document=result.document,
        metadata=result.metadata,
        warnings=result.warnings,
    )


@router.get(
    "/{document_id}/file",
    response_model=FileUrlResponse,
    summary="Short-lived URL to view the original file",
)
def get_file_url(
    document_id: str, user: ReadUser, repository: RepositoryDep, storage: StorageDep
) -> FileUrlResponse:
    record = owned_record(repository, document_id, user)
    if record.status is DocumentStatus.AWAITING_UPLOAD:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The file has not been uploaded yet.")
    signed = storage.download_url(record.object_name, filename=record.original_filename)
    return FileUrlResponse(
        url=signed.url, expires_at=signed.expires_at, content_type=record.content_type
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Permanently delete a document, its file and its analytics rows",
    responses={
        404: {"description": "Not found"},
        409: {"description": "Upload or processing still in progress; try again later"},
    },
)
def delete_document_endpoint(
    document_id: str,
    user: Annotated[CurrentUser, Depends(rate_limit("review_write"))],
    repository: RepositoryDep,
    storage: StorageDep,
    analytics: AnalyticsWriterDep,
) -> Response:
    record = owned_record(repository, document_id, user)
    try:
        delete_document(record, repository=repository, storage=storage, analytics=analytics)
    except DocumentBusyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
