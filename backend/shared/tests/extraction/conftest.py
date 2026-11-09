"""Fixtures that build small, valid documents in memory (no binary files in the repo)."""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from PIL import Image
from pypdf import PdfWriter

from receipt_shared.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        gcp_project_id="test-project",
        gemini_model="gemini-test",
        gemini_location="us-central1",
        gemini_max_retries=3,
        max_upload_bytes=2 * 1024 * 1024,
        max_pdf_pages=3,
        max_image_pixels=4_000_000,
    )


def make_image(fmt: str = "PNG", size: tuple[int, int] = (200, 300)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, fmt)
    return buf.getvalue()


def make_pdf(pages: int = 1, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if password is not None:
        writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def image_factory() -> Callable[..., bytes]:
    return make_image


@pytest.fixture
def pdf_factory() -> Callable[..., bytes]:
    return make_pdf


@pytest.fixture
def png_bytes() -> bytes:
    return make_image("PNG")


@pytest.fixture
def jpeg_bytes() -> bytes:
    return make_image("JPEG")


@pytest.fixture
def pdf_bytes() -> bytes:
    return make_pdf(2)
