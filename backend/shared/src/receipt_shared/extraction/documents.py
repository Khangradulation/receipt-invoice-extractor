"""Inspect and validate an input document before it is sent to Gemini.

The file type is decided by the file's magic bytes, not by its name or declared content type;
a mismatch between them is rejected. PDFs are opened to count pages and to detect encryption or
corruption; images are decoded to check integrity and dimensions.
"""

from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import PurePath

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from receipt_shared.config import Settings
from receipt_shared.extraction.errors import (
    CorruptDocumentError,
    FileTooLargeError,
    InvalidDocumentError,
    TooManyPagesError,
    UnsupportedFileTypeError,
)
from receipt_shared.files import (
    EXTENSION_MIME,
    JPEG,
    PDF,
    PNG,
    SUPPORTED_MIME_TYPES,
    normalize_mime,
)

__all__ = ["JPEG", "PDF", "PNG", "SUPPORTED_MIME_TYPES", "DocumentInput", "inspect_document"]


@dataclass(frozen=True, slots=True)
class DocumentInput:
    """A validated document ready for extraction."""

    data: bytes
    mime_type: str
    sha256: str
    size_bytes: int
    page_count: int  # 1 for images
    filename: str | None = None
    # If set, Gemini reads the object from Cloud Storage instead of receiving inline bytes.
    gcs_uri: str | None = None


def sniff_mime_type(data: bytes) -> str | None:
    """Identify PDF / PNG / JPEG from magic bytes."""
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    # Some PDF writers emit a few junk bytes before the header; the spec allows up to 1024.
    if b"%PDF-" in data[:1024]:
        return PDF
    return None


def _count_pdf_pages(data: bytes) -> int:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise InvalidDocumentError("Password-protected PDFs are not supported.")
        pages = len(reader.pages)
    except InvalidDocumentError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise CorruptDocumentError("The PDF could not be read; it may be damaged.") from exc
    if pages == 0:
        raise CorruptDocumentError("The PDF has no pages.")
    return pages


def _check_image(data: bytes, max_pixels: int) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as img:
                width, height = img.size
                if width * height > max_pixels:
                    raise InvalidDocumentError(
                        f"Image is too large ({width}x{height} pixels; limit {max_pixels:,})."
                    )
                img.verify()  # integrity check without a full decode
    except InvalidDocumentError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidDocumentError("Image dimensions exceed the allowed limit.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise CorruptDocumentError("The image could not be decoded; it may be damaged.") from exc


def inspect_document(
    data: bytes,
    settings: Settings,
    *,
    filename: str | None = None,
    declared_mime_type: str | None = None,
    gcs_uri: str | None = None,
) -> DocumentInput:
    """Validate ``data`` and return a ``DocumentInput``, or raise ``InvalidDocumentError``."""
    size = len(data)
    if size == 0:
        raise InvalidDocumentError("The file is empty.")
    if size > settings.max_upload_bytes:
        raise FileTooLargeError(
            f"File is {size:,} bytes; the limit is {settings.max_upload_bytes:,} bytes."
        )

    mime = sniff_mime_type(data)
    if mime is None:
        raise UnsupportedFileTypeError("Unsupported file type. Upload a PDF, PNG or JPEG.")

    if filename is not None:
        ext = PurePath(filename).suffix.lower()
        expected = EXTENSION_MIME.get(ext)
        if expected is None:
            raise UnsupportedFileTypeError(
                f"Unsupported file extension '{ext or '(none)'}'. Use .pdf, .png, .jpg or .jpeg."
            )
        if expected != mime:
            raise UnsupportedFileTypeError(
                f"File content ({mime}) does not match its extension '{ext}'."
            )

    if declared_mime_type is not None:
        declared = normalize_mime(declared_mime_type)
        if declared != mime:
            raise UnsupportedFileTypeError(
                f"File content ({mime}) does not match the declared type '{declared}'."
            )

    if mime == PDF:
        pages = _count_pdf_pages(data)
        if pages > settings.max_pdf_pages:
            raise TooManyPagesError(
                f"PDF has {pages} pages; the limit is {settings.max_pdf_pages}."
            )
    else:
        _check_image(data, settings.max_image_pixels)
        pages = 1

    return DocumentInput(
        data=data,
        mime_type=mime,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=size,
        page_count=pages,
        filename=filename,
        gcs_uri=gcs_uri,
    )
