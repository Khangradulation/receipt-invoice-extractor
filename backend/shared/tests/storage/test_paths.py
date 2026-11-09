import pytest

from receipt_shared.storage import (
    parse_upload_object_name,
    processed_prefix,
    sanitize_filename,
    upload_object_name,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("receipt.pdf", "receipt.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("..\\..\\windows\\evil.png", "evil.png"),
        ("Reçu été 2026.PDF", "Recu_ete_2026.pdf"),
        ("my receipt (1).jpeg", "my_receipt_1.jpeg"),
        (".hidden.png", "hidden.png"),
        ("noext", "noext"),
        ("....pdf", "document.pdf"),
        ("家計簿.jpg", "document.jpg"),
        ("a/b/c/../d.pdf", "d.pdf"),
    ],
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_long_filenames_are_truncated_keeping_extension() -> None:
    name = sanitize_filename("x" * 500 + ".pdf")
    assert len(name) <= 120
    assert name.endswith(".pdf")


def test_upload_object_name_layout() -> None:
    assert (
        upload_object_name("user_1", "abc123", "Receipt 1.pdf")
        == "uploads/user_1/abc123/Receipt_1.pdf"
    )


@pytest.mark.parametrize("bad", ["", "a/b", "../x", "a b", "x" * 129])
def test_ids_with_path_characters_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid user_id"):
        upload_object_name(bad, "doc", "a.pdf")
    with pytest.raises(ValueError, match="invalid document_id"):
        upload_object_name("user", bad, "a.pdf")


def test_parse_round_trip() -> None:
    parsed = parse_upload_object_name(upload_object_name("u1", "d1", "a.png"))
    assert parsed is not None
    assert (parsed.user_id, parsed.document_id, parsed.filename) == ("u1", "d1", "a.png")


@pytest.mark.parametrize(
    "name",
    [
        "processed/u1/d1/extraction.json",
        "evaluation/x.pdf",
        "uploads/u1/d1",
        "uploads/u1/d1/sub/a.pdf",
        "uploads/u 1/d1/a.pdf",
        "uploads//d1/a.pdf",
    ],
)
def test_parse_ignores_non_upload_objects(name: str) -> None:
    assert parse_upload_object_name(name) is None


def test_processed_prefix() -> None:
    assert processed_prefix("u1", "d1") == "processed/u1/d1/"
