from run_benchmark import select_documents

MANIFEST = [
    {"name": "r1", "document_type": "receipt"},
    {"name": "i1", "document_type": "invoice"},
    {"name": "i2", "document_type": "invoice"},
]


def names(items: list[dict[str, str]]) -> list[str]:
    return [i["name"] for i in items]


def test_selects_one_document_type() -> None:
    assert names(select_documents(MANIFEST, "invoice", None)) == ["i1", "i2"]


def test_no_filter_keeps_everything() -> None:
    assert names(select_documents(MANIFEST, None, None)) == ["r1", "i1", "i2"]


def test_limit_applies_after_the_filter() -> None:
    assert names(select_documents(MANIFEST, "invoice", 1)) == ["i1"]
