"""Shared FastAPI dependencies. Clients are created lazily and cached on ``app.state``."""

from __future__ import annotations

import threading
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from receipt_api.review_service import ReviewService
from receipt_shared.analytics import AnalyticsQueries, BigQueryAnalyticsWriter
from receipt_shared.config import Settings
from receipt_shared.repository import DocumentRepository, FirestoreDocumentRepository
from receipt_shared.storage import DocumentStorage, StorageNotConfiguredError

_lock = threading.RLock()


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_storage(request: Request) -> DocumentStorage:
    with _lock:
        storage: DocumentStorage | None = getattr(request.app.state, "storage", None)
        if storage is None:
            try:
                storage = DocumentStorage(request.app.state.settings)
            except StorageNotConfiguredError as exc:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is not configured."
                ) from exc
            request.app.state.storage = storage
    return storage


def get_repository(request: Request) -> DocumentRepository:
    repo: DocumentRepository | None = getattr(request.app.state, "repository", None)
    if repo is None:
        repo = FirestoreDocumentRepository.from_settings(request.app.state.settings)
        request.app.state.repository = repo
    return repo


def get_analytics_writer(request: Request) -> BigQueryAnalyticsWriter:
    with _lock:
        writer: BigQueryAnalyticsWriter | None = getattr(
            request.app.state, "analytics_writer", None
        )
        if writer is None:
            writer = BigQueryAnalyticsWriter(request.app.state.settings)
            request.app.state.analytics_writer = writer
    return writer


def get_review_service(request: Request) -> ReviewService:
    with _lock:
        service: ReviewService | None = getattr(request.app.state, "review_service", None)
        if service is None:
            from receipt_shared.validation import DocumentValidator

            settings = request.app.state.settings
            service = ReviewService(
                repository=get_repository(request),
                validator=DocumentValidator(settings=settings),
                writer=get_analytics_writer(request),
            )
            request.app.state.review_service = service
    return service


def get_analytics(request: Request) -> AnalyticsQueries:
    with _lock:
        queries: AnalyticsQueries | None = getattr(request.app.state, "analytics", None)
        if queries is None:
            queries = AnalyticsQueries(request.app.state.settings)
            request.app.state.analytics = queries
    return queries


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
StorageDep = Annotated[DocumentStorage, Depends(get_storage)]
RepositoryDep = Annotated[DocumentRepository, Depends(get_repository)]
ReviewServiceDep = Annotated[ReviewService, Depends(get_review_service)]
AnalyticsDep = Annotated[AnalyticsQueries, Depends(get_analytics)]
AnalyticsWriterDep = Annotated[BigQueryAnalyticsWriter, Depends(get_analytics_writer)]
