"""Ownership checks: users can only ever see their own documents."""

from __future__ import annotations

import re

from fastapi import HTTPException, status

from receipt_api.auth import CurrentUser
from receipt_shared.repository import DocumentRecord, DocumentRepository

_DOC_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def owned_record(repo: DocumentRepository, document_id: str, user: CurrentUser) -> DocumentRecord:
    """Return the record if it belongs to ``user``.

    Missing and foreign documents both produce the same 404, so the API never reveals that
    another user's document exists.
    """
    record = repo.get(document_id) if _DOC_ID.match(document_id) else None
    if record is None or record.user_id != user.uid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return record
