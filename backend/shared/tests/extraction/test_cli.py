import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from receipt_shared.config import Settings, get_settings
from receipt_shared.extraction import cli
from receipt_shared.extraction.documents import DocumentInput
from receipt_shared.models.extraction import (
    ExtractedDocument,
    ExtractionMetadata,
    ExtractionResult,
)


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    get_settings.cache_clear()


def _outputs(text: str) -> list[dict[str, Any]]:
    decoder, out, i = json.JSONDecoder(), [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        obj, i = decoder.raw_decode(text, i)
        out.append(obj)
    return out


def test_inspect_only(tmp_path: Path, png_bytes: bytes, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "r.png"
    f.write_bytes(png_bytes)
    assert cli.main(["--inspect-only", str(f)]) == 0
    [out] = _outputs(capsys.readouterr().out)
    assert out["file_info"]["mime_type"] == "image/png"
    assert "result" not in out


def test_invalid_file_reports_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "r.gif"
    f.write_bytes(b"GIF89a" + b"\0" * 64)
    assert cli.main(["--inspect-only", str(f)]) == 1
    [out] = _outputs(capsys.readouterr().out)
    assert out["error"]["code"] == "unsupported_file_type"


def test_missing_file_reports_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--inspect-only", str(tmp_path / "nope.pdf")]) == 1
    [out] = _outputs(capsys.readouterr().out)
    assert out["error"]["code"] == "file_error"


def test_extraction_with_model_override(
    tmp_path: Path,
    pdf_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: dict[str, Any] = {}

    class StubExtractor:
        def __init__(self, settings: Settings) -> None:
            seen["model"] = settings.gemini_model

        def extract(
            self, document: DocumentInput, *, document_id: str | None = None
        ) -> ExtractionResult:
            return ExtractionResult(
                document=ExtractedDocument(total_amount=Decimal("12.50")),
                metadata=ExtractionMetadata(
                    model=seen["model"], prompt_version="p", location="l", latency_ms=1, attempts=1
                ),
            )

    monkeypatch.setattr(cli, "GeminiExtractor", StubExtractor)
    f = tmp_path / "inv.pdf"
    f.write_bytes(pdf_bytes)
    assert cli.main(["--model", "gemini-other", str(f)]) == 0
    [out] = _outputs(capsys.readouterr().out)
    assert seen["model"] == "gemini-other"
    assert out["result"]["document"]["total_amount"] == "12.50"
    assert out["file_info"]["page_count"] == 2
