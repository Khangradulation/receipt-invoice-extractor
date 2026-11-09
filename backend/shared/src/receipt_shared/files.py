"""Supported upload types (shared by the API's request validation and the extraction engine)."""

from __future__ import annotations

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
SUPPORTED_MIME_TYPES: frozenset[str] = frozenset({PDF, PNG, JPEG})
EXTENSION_MIME: dict[str, str] = {".pdf": PDF, ".png": PNG, ".jpg": JPEG, ".jpeg": JPEG}
_MIME_ALIASES = {"image/jpg": JPEG, "image/pjpeg": JPEG}


def normalize_mime(value: str) -> str:
    """'Image/JPG; charset=x' -> 'image/jpeg'."""
    mime = value.split(";", 1)[0].strip().lower()
    return _MIME_ALIASES.get(mime, mime)
