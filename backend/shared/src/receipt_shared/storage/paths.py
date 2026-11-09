"""Object naming in the documents bucket.

uploads/{user_id}/{document_id}/{filename}      original documents (written via signed URL)
processed/{user_id}/{document_id}/...           worker outputs (Phase 5)
evaluation/...                                  benchmark documents (Phase 10)
tmp/...                                         scratch, deleted after 1 day by lifecycle
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

UPLOADS_PREFIX = "uploads/"
PROCESSED_PREFIX = "processed/"
EVALUATION_PREFIX = "evaluation/"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_FILENAME_LENGTH = 120


def _check_id(value: str, what: str) -> str:
    if not _ID_RE.match(value):
        raise ValueError(f"invalid {what} for an object path")
    return value


def sanitize_filename(filename: str) -> str:
    """Make a user-supplied filename safe as the last path segment, keeping its extension.

    '../../etc/passwd' -> 'passwd'; 'Reçu été 2026.PDF' -> 'Recu_ete_2026.pdf'.
    """
    base = PurePosixPath(filename.replace("\\", "/")).name
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    ext = _UNSAFE.sub("", ext).lower()[:10]
    stem = _UNSAFE.sub("_", stem).strip("._-")
    stem = stem[: MAX_FILENAME_LENGTH - len(ext) - 1] or "document"
    return f"{stem}.{ext}" if ext else stem


def upload_object_name(user_id: str, document_id: str, filename: str) -> str:
    return (
        f"{UPLOADS_PREFIX}{_check_id(user_id, 'user_id')}/"
        f"{_check_id(document_id, 'document_id')}/{sanitize_filename(filename)}"
    )


def processed_prefix(user_id: str, document_id: str) -> str:
    return (
        f"{PROCESSED_PREFIX}{_check_id(user_id, 'user_id')}/"
        f"{_check_id(document_id, 'document_id')}/"
    )


@dataclass(frozen=True)
class UploadPath:
    user_id: str
    document_id: str
    filename: str


def parse_upload_object_name(name: str) -> UploadPath | None:
    """Parse ``uploads/{user}/{doc}/{file}``; ``None`` for anything else (e.g. processed/)."""
    if not name.startswith(UPLOADS_PREFIX):
        return None
    parts = name[len(UPLOADS_PREFIX) :].split("/")
    if len(parts) != 3 or not all(parts):
        return None
    user_id, document_id, filename = parts
    if not (_ID_RE.match(user_id) and _ID_RE.match(document_id)):
        return None
    return UploadPath(user_id, document_id, filename)
