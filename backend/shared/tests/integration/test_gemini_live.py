"""Live Gemini extraction against Vertex AI. Opt-in: incurs (small) Vertex AI charges.

    cd backend
    uv run python ../evaluation/samples/generate_samples.py
    RUN_GEMINI_INTEGRATION=1 GCP_PROJECT_ID=your-project uv run pytest -m integration -v

Requires Application Default Credentials with permission to call Vertex AI.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from receipt_shared.config import Settings
from receipt_shared.extraction import GeminiExtractor, inspect_document

SAMPLES = Path(__file__).resolve().parents[4] / "evaluation" / "samples" / "out"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_GEMINI_INTEGRATION") != "1",
        reason="set RUN_GEMINI_INTEGRATION=1 to call the real Gemini API",
    ),
]


@pytest.fixture(scope="module")
def extractor() -> GeminiExtractor:
    settings = Settings()
    if not settings.gcp_project_id:
        pytest.skip("GCP_PROJECT_ID is not set")
    return GeminiExtractor(settings)


def _truth(name: str) -> dict[str, object]:
    path = SAMPLES / f"{name}.truth.json"
    if not path.exists():
        pytest.skip("sample documents not generated; run evaluation/samples/generate_samples.py")
    return json.loads(path.read_text())  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "filename",
    [
        "receipt_cafe.png",
        "receipt_cafe.jpg",
        "receipt_cafe.pdf",
        "receipt_hardware_discount.pdf",
        "invoice_consulting_2pages.pdf",
    ],
)
def test_extracts_core_fields(extractor: GeminiExtractor, filename: str) -> None:
    name = filename.rsplit(".", 1)[0]
    truth = _truth(name)
    data = (SAMPLES / filename).read_bytes()
    doc = inspect_document(data, Settings(), filename=filename)
    result = extractor.extract(doc, document_id=f"it-{name}")
    d = result.document

    assert d.document_type == truth["document_type"]
    assert d.currency == truth["currency"]
    assert str(d.document_date) == truth["document_date"]
    assert d.total_amount == Decimal(str(truth["total_amount"]))
    assert d.subtotal == Decimal(str(truth["subtotal"]))
    assert len(d.line_items) == len(truth["line_items"])  # type: ignore[arg-type]
    assert result.metadata.model_version


def test_ignores_prompt_injection(extractor: GeminiExtractor) -> None:
    truth = _truth("receipt_prompt_injection")
    data = (SAMPLES / "receipt_prompt_injection.png").read_bytes()
    doc = inspect_document(data, Settings(), filename="receipt_prompt_injection.png")
    d = extractor.extract(doc, document_id="it-injection").document
    assert d.merchant_name == truth["merchant_name"]
    assert d.total_amount == Decimal(str(truth["total_amount"]))
