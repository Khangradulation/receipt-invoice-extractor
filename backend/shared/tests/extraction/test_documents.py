from collections.abc import Callable

import pytest

from receipt_shared.config import Settings
from receipt_shared.extraction.documents import JPEG, PDF, PNG, inspect_document, sniff_mime_type
from receipt_shared.extraction.errors import (
    CorruptDocumentError,
    FileTooLargeError,
    InvalidDocumentError,
    TooManyPagesError,
    UnsupportedFileTypeError,
)

Factory = Callable[..., bytes]


def test_sniff_mime_types(png_bytes: bytes, jpeg_bytes: bytes, pdf_bytes: bytes) -> None:
    assert sniff_mime_type(png_bytes) == PNG
    assert sniff_mime_type(jpeg_bytes) == JPEG
    assert sniff_mime_type(pdf_bytes) == PDF
    assert sniff_mime_type(b"GIF89a....") is None
    assert sniff_mime_type(b"\x00\x00junk%PDF-1.7") == PDF  # header within first 1024 bytes


def test_pdf_is_accepted_with_page_count(settings: Settings, pdf_bytes: bytes) -> None:
    doc = inspect_document(pdf_bytes, settings, filename="r.pdf", declared_mime_type=PDF)
    assert doc.mime_type == PDF
    assert doc.page_count == 2
    assert doc.size_bytes == len(pdf_bytes)
    assert len(doc.sha256) == 64


@pytest.mark.parametrize(
    ("fmt", "name", "declared"),
    [("PNG", "a.png", "image/png"), ("JPEG", "a.JPG", "image/jpg"), ("JPEG", "a.jpeg", None)],
)
def test_images_are_accepted(
    settings: Settings, image_factory: Factory, fmt: str, name: str, declared: str | None
) -> None:
    doc = inspect_document(image_factory(fmt), settings, filename=name, declared_mime_type=declared)
    assert doc.page_count == 1


def test_empty_file_rejected(settings: Settings) -> None:
    with pytest.raises(InvalidDocumentError, match="empty"):
        inspect_document(b"", settings)


def test_too_large_rejected(settings: Settings) -> None:
    data = b"%PDF-1.7" + b"0" * settings.max_upload_bytes
    with pytest.raises(FileTooLargeError):
        inspect_document(data, settings)


def test_unknown_content_rejected(settings: Settings) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        inspect_document(b"GIF89a" + b"\x00" * 100, settings)


def test_unsupported_extension_rejected(settings: Settings, png_bytes: bytes) -> None:
    with pytest.raises(UnsupportedFileTypeError, match=r"\.exe"):
        inspect_document(png_bytes, settings, filename="receipt.exe")


def test_extension_content_mismatch_rejected(settings: Settings, png_bytes: bytes) -> None:
    with pytest.raises(UnsupportedFileTypeError, match="does not match its extension"):
        inspect_document(png_bytes, settings, filename="receipt.pdf")


def test_declared_type_mismatch_rejected(settings: Settings, pdf_bytes: bytes) -> None:
    with pytest.raises(UnsupportedFileTypeError, match="declared type"):
        inspect_document(pdf_bytes, settings, declared_mime_type="image/png")


def test_too_many_pages_rejected(settings: Settings, pdf_factory: Factory) -> None:
    with pytest.raises(TooManyPagesError, match="4 pages"):
        inspect_document(pdf_factory(4), settings)


def test_encrypted_pdf_rejected(settings: Settings, pdf_factory: Factory) -> None:
    with pytest.raises(InvalidDocumentError, match="Password-protected"):
        inspect_document(pdf_factory(1, password="secret"), settings)


def test_corrupt_pdf_rejected(settings: Settings) -> None:
    with pytest.raises(CorruptDocumentError):
        inspect_document(b"%PDF-1.7\n" + b"garbage" * 50, settings)


def test_truncated_image_rejected(settings: Settings, png_bytes: bytes) -> None:
    with pytest.raises(CorruptDocumentError):
        inspect_document(png_bytes[:60], settings)


def test_oversized_image_rejected(settings: Settings, image_factory: Factory) -> None:
    big = image_factory("PNG", size=(3000, 2000))  # 6 MP > 4 MP limit in the fixture
    with pytest.raises(InvalidDocumentError, match="too large"):
        inspect_document(big, settings)


def test_gcs_uri_is_carried(settings: Settings, png_bytes: bytes) -> None:
    doc = inspect_document(png_bytes, settings, gcs_uri="gs://bucket/uploads/u/d/a.png")
    assert doc.gcs_uri == "gs://bucket/uploads/u/d/a.png"
