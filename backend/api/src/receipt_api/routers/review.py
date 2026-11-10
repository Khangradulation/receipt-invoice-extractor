"""Manual review endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from receipt_api.auth import CurrentUser
from receipt_api.deps import RepositoryDep, ReviewServiceDep
from receipt_api.ownership import owned_record
from receipt_api.ratelimit import rate_limit
from receipt_api.review_service import ReviewService, ReviewState
from receipt_api.routers.documents import detail
from receipt_api.schemas import (
    Correction,
    CorrectionRequest,
    DocumentPage,
    RejectRequest,
    ReviewDetail,
    summary,
)
from receipt_shared.models.enums import DocumentStatus
from receipt_shared.repository import InvalidCursorError

router = APIRouter(prefix="/review", tags=["review"])

ReadUser = Annotated[CurrentUser, Depends(rate_limit("read"))]
WriteUser = Annotated[CurrentUser, Depends(rate_limit("review_write"))]


def review_detail(state: ReviewState, service: ReviewService) -> ReviewDetail:
    validation = state.validation
    return ReviewDetail(
        document=detail(state.record, service),
        original=state.original,
        current=state.corrected or state.original,
        validation=validation,
        failed_fields=list(validation.failed_fields) if validation else [],
        corrections=[
            Correction.model_validate(c)
            for c in state.corrections
            if c.get("action") == "CORRECTION"
        ],
        duplicate_acknowledged=state.duplicate_acknowledged,
        can_approve=bool(
            state.record.status is DocumentStatus.REVIEW_REQUIRED
            and validation
            and validation.is_valid
        ),
    )


@router.get("", response_model=DocumentPage, summary="Your review queue (newest first)")
def review_queue(
    user: ReadUser,
    repository: RepositoryDep,
    service: ReviewServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> DocumentPage:
    try:
        page = repository.list_for_user(
            user.uid, statuses=[DocumentStatus.REVIEW_REQUIRED], limit=limit, cursor=cursor
        )
    except InvalidCursorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid page cursor.") from exc
    return DocumentPage(
        items=[summary(r, service.effective(r)) for r in page.items], next_cursor=page.next_cursor
    )


@router.get("/{document_id}", response_model=ReviewDetail, summary="Review a document")
def get_review(
    document_id: str, user: ReadUser, repository: RepositoryDep, service: ReviewServiceDep
) -> ReviewDetail:
    record = owned_record(repository, document_id, user)
    return review_detail(service.state(record), service)


@router.patch(
    "/{document_id}",
    response_model=ReviewDetail,
    summary="Save corrections (revalidates; does not approve)",
    responses={409: {"description": "Not in review"}, 422: {"description": "Invalid values"}},
)
def save_corrections(
    document_id: str,
    body: CorrectionRequest,
    user: WriteUser,
    repository: RepositoryDep,
    service: ReviewServiceDep,
) -> ReviewDetail:
    record = owned_record(repository, document_id, user)
    state = service.save_corrections(
        record,
        reviewer_id=user.uid,
        fields=body.fields,
        acknowledge_duplicate=body.acknowledge_duplicate,
    )
    return review_detail(state, service)


@router.post(
    "/{document_id}/approve",
    response_model=ReviewDetail,
    summary="Approve (only when validation passes); loads the record into BigQuery",
    responses={409: {"description": "Not in review, or validation errors remain"}},
)
def approve(
    document_id: str, user: WriteUser, repository: RepositoryDep, service: ReviewServiceDep
) -> ReviewDetail:
    record = owned_record(repository, document_id, user)
    return review_detail(service.approve(record, reviewer_id=user.uid), service)


@router.post(
    "/{document_id}/reject",
    response_model=ReviewDetail,
    summary="Reject with a reason",
    responses={409: {"description": "Not rejectable in its current status"}},
)
def reject(
    document_id: str,
    body: RejectRequest,
    user: WriteUser,
    repository: RepositoryDep,
    service: ReviewServiceDep,
) -> ReviewDetail:
    record = owned_record(repository, document_id, user)
    return review_detail(
        service.reject(record, reviewer_id=user.uid, reason=body.reason.strip()), service
    )
