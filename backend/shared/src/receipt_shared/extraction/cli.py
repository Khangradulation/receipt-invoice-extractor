"""Command-line extraction for local testing.

    uv run receipt-extract path/to/receipt.pdf [more files...]
    uv run receipt-extract --inspect-only samples/*.png     # file checks only, no Gemini call
    uv run receipt-extract --model gemini-2.5-pro invoice.pdf

Prints one JSON object per file to stdout (logs go to stderr). Calls to Gemini are billed to
the configured GCP project and need Application Default Credentials
(``gcloud auth application-default login``).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

from receipt_shared.config import get_settings
from receipt_shared.extraction.documents import inspect_document
from receipt_shared.extraction.errors import ExtractionError
from receipt_shared.extraction.gemini import GeminiExtractor
from receipt_shared.logging import JsonFormatter


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="receipt-extract", description=__doc__.split("\n\n")[0])
    p.add_argument("files", nargs="+", type=Path, help="PDF, PNG or JPEG files")
    p.add_argument("--model", help="Override GEMINI_MODEL")
    p.add_argument("--location", help="Override GEMINI_LOCATION")
    p.add_argument(
        "--inspect-only", action="store_true", help="Validate the files without calling Gemini"
    )
    p.add_argument("--log-level", default="WARNING", help="Log level for stderr (default WARNING)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter("extract-cli"))
    logging.basicConfig(level=args.log_level.upper(), handlers=[handler], force=True)

    overrides: dict[str, Any] = {}
    if args.model:
        overrides["gemini_model"] = args.model
    if args.location:
        overrides["gemini_location"] = args.location
    settings = get_settings().model_copy(update=overrides)

    extractor: GeminiExtractor | None = None
    exit_code = 0
    for path in args.files:
        out: dict[str, Any] = {"file": str(path)}
        try:
            document = inspect_document(path.read_bytes(), settings, filename=path.name)
            out["file_info"] = {
                "mime_type": document.mime_type,
                "size_bytes": document.size_bytes,
                "page_count": document.page_count,
                "sha256": document.sha256,
            }
            if not args.inspect_only:
                extractor = extractor or GeminiExtractor(settings)
                result = extractor.extract(document, document_id=f"cli-{uuid.uuid4().hex[:12]}")
                out["result"] = result.model_dump(mode="json")
        except ExtractionError as exc:
            exit_code = 1
            out["error"] = {"code": exc.code, "message": exc.message, "retryable": exc.retryable}
        except OSError as exc:
            exit_code = 1
            out["error"] = {"code": "file_error", "message": str(exc), "retryable": False}
        print(json.dumps(out, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
