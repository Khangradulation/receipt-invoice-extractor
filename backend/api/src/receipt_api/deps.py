"""Shared FastAPI dependencies. Clients are created lazily and cached on ``app.state``."""

from __future__ import annotations

import threading
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from receipt_shared.config import Settings
from receipt_shared.repository import DocumentRepository, FirestoreDocumentRepository
from receipt_shared.storage import DocumentStorage, StorageNotConfiguredError

_lock = threading.Lock()


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
    with _lock:
        repo: DocumentRepository | None = getattr(request.app.state, "repository", None)
        if repo is None:
            repo = FirestoreDocumentRepository.from_settings(request.app.state.settings)
            request.app.state.repository = repo
    return repo


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
StorageDep = Annotated[DocumentStorage, Depends(get_storage)]
RepositoryDep = Annotated[DocumentRepository, Depends(get_repository)]
