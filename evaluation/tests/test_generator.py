import json
from decimal import Decimal
from pathlib import Path

import pytest

from generate import Doc, ascii_only, build_dataset, main


def test_dataset_is_deterministic() -> None:
    a = [d.truth() for d in build_dataset(30, seed=1)]
    b = [d.truth() for d in build_dataset(30, seed=1)]
    c = [d.truth() for d in build_dataset(30, seed=2)]
    assert a == b
    assert a != c


def test_mix_and_edge_cases() -> None:
    docs = build_dataset(150, seed=20261110)
    assert sum(d.kind == "invoice" for d in docs) == 60
    assert sum("prompt_injection" in d.tags for d in docs) == 5
    assert sum("total_mismatch" in d.tags for d in docs) == 5
    assert len({d.locale.currency for d in docs}) == 8


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_ground_truth_arithmetic_matches_what_is_printed(seed: int) -> None:
    for d in build_dataset(60, seed=seed):
        t = d.truth()
        lines = sum(Decimal(li["total_price"]) for li in t["line_items"])
        assert Decimal(t["subtotal"]) == lines
        discount = Decimal(t["discount_amount"] or 0)
        tax = Decimal(t["tax_amount"] or 0)
        expected = Decimal(t["subtotal"]) - discount + (0 if d.locale.tax_inclusive else tax)
        mismatch = "total_mismatch" in d.tags
        assert (Decimal(t["total_amount"]) != expected) is mismatch, d.name
        assert len({li["description"] for li in t["line_items"]}) == len(t["line_items"])
        if d.kind == "receipt":
            assert t["due_date"] is None
        else:
            assert t["due_date"]
            assert t["document_number"]


def test_unprinted_quantities_are_null_in_truth() -> None:
    docs = [d for d in build_dataset(150, seed=20261110) if "qty_not_printed" in d.tags]
    assert docs
    assert any(li["quantity"] is None for d in docs for li in d.truth()["line_items"])


def test_ascii_guard() -> None:
    assert ascii_only("Total 26.68") == "Total 26.68"
    with pytest.raises(ValueError, match="non-ASCII"):
        ascii_only("Total 26,68 €")


def test_writes_files_truth_and_manifest(tmp_path: Path) -> None:
    assert main(["--count", "12", "--seed", "5", "--out", str(tmp_path)]) == 0
    manifest = [json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert len(manifest) == 12
    for m in manifest:
        assert (tmp_path / m["file"]).stat().st_size > 1000
        truth = json.loads((tmp_path / f"{m['name']}.truth.json").read_text())
        assert truth["document_type"] == m["document_type"]
        if m["pages"] > 1:
            assert m["format"] == "pdf"
    assert json.loads((tmp_path / "dataset.json").read_text())["count"] == 12


def test_doc_type_is_importable() -> None:
    assert Doc.__name__ == "Doc"
