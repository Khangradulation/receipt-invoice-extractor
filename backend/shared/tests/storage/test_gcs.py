import hashlib
import io
from typing import Any

import pytest
from pypdf import PdfWriter

from receipt_shared.config import Settings
from receipt_shared.extraction.errors import UnsupportedFileTypeError
from receipt_shared.storage import DocumentStorage, StorageNotConfiguredError
from receipt_shared.storage.gcs import ObjectTooLargeError, StoredObject, content_disposition
from receipt_shared.storage.verify import IntegrityError, verify_upload


class FakeCredentials:
    def __init__(self, valid: bool = False) -> None:
        self.valid = valid
        self.token = "tok-0"
        self.refreshes = 0

    def refresh(self, request: object) -> None:
        self.refreshes += 1
        self.token = f"tok-{self.refreshes}"
        self.valid = True


class FakeBlob:
    def __init__(self, name: str, *, size: int = 10, data: bytes = b"x") -> None:
        self.name = name
        self.size = size
        self.generation = 7
        self.content_type = "application/pdf"
        self.metadata: dict[str, str] = {}
        self._data = data
        self.signed_calls: list[dict[str, Any]] = []

    def generate_signed_url(self, **kwargs: Any) -> str:
        self.signed_calls.append(kwargs)
        return f"https://storage.googleapis.com/bucket/{self.name}?X-Goog-Signature=abc"

    def download_as_bytes(self, checksum: str | None = None) -> bytes:
        assert checksum == "crc32c"
        return self._data


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str) -> FakeBlob:
        return self.blobs.setdefault(name, FakeBlob(name))

    def get_blob(self, name: str, generation: int | None = None) -> FakeBlob | None:
        return self.blobs.get(name)


class FakeClient:
    def __init__(self) -> None:
        self.bucket_obj = FakeBucket()

    def bucket(self, name: str) -> FakeBucket:
        return self.bucket_obj


def settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "_env_file": None,
        "gcs_upload_bucket": "docs-bucket",
        "signing_service_account": "api@p.iam.gserviceaccount.com",
        "signed_url_ttl_seconds": 600,
        "max_upload_bytes": 1000,
    }
    base.update(overrides)
    return Settings(**base)


def make_storage(**overrides: Any) -> tuple[DocumentStorage, FakeClient, FakeCredentials]:
    client, creds = FakeClient(), FakeCredentials()
    storage = DocumentStorage(settings(**overrides), client=client, credentials=creds)  # type: ignore[arg-type]
    return storage, client, creds


def test_requires_bucket() -> None:
    with pytest.raises(StorageNotConfiguredError, match="GCS_UPLOAD_BUCKET"):
        DocumentStorage(
            settings(gcs_upload_bucket=None), client=FakeClient(), credentials=FakeCredentials()
        )  # type: ignore[arg-type]


def test_upload_url_binds_type_and_exact_size_and_signs_via_iam() -> None:
    storage, client, creds = make_storage()
    signed = storage.upload_url("uploads/u/d/a.pdf", content_type="application/pdf", size_bytes=123)
    [call] = client.bucket_obj.blobs["uploads/u/d/a.pdf"].signed_calls
    assert call["version"] == "v4"
    assert call["method"] == "PUT"
    assert call["content_type"] == "application/pdf"
    assert call["headers"] == {"x-goog-content-length-range": "123,123"}
    assert call["service_account_email"] == "api@p.iam.gserviceaccount.com"
    assert call["access_token"] == "tok-1"
    assert call["expiration"].total_seconds() == 600
    assert signed.method == "PUT"
    assert signed.headers == {
        "Content-Type": "application/pdf",
        "x-goog-content-length-range": "123,123",
    }
    assert creds.refreshes == 1


def test_token_is_reused_while_valid() -> None:
    storage, _, creds = make_storage()
    storage.upload_url("uploads/u/d/a.pdf", content_type="application/pdf", size_bytes=1)
    storage.upload_url("uploads/u/d/b.pdf", content_type="application/pdf", size_bytes=1)
    assert creds.refreshes == 1


def test_signing_requires_service_account() -> None:
    storage, _, _ = make_storage(signing_service_account=None)
    with pytest.raises(StorageNotConfiguredError, match="SIGNING_SERVICE_ACCOUNT"):
        storage.upload_url("uploads/u/d/a.pdf", content_type="application/pdf", size_bytes=1)


def test_download_url_is_inline_get() -> None:
    storage, client, _ = make_storage()
    signed = storage.download_url("uploads/u/d/a.pdf", filename="a.pdf")
    [call] = client.bucket_obj.blobs["uploads/u/d/a.pdf"].signed_calls
    assert call["method"] == "GET"
    assert call["response_disposition"] == "inline; filename=\"a.pdf\"; filename*=UTF-8''a.pdf"
    assert signed.method == "GET"


def test_read_refuses_oversized_objects() -> None:
    storage, client, _ = make_storage()
    client.bucket_obj.blobs["big"] = FakeBlob("big", size=5000)
    with pytest.raises(ObjectTooLargeError):
        storage.read("big")


def test_read_missing_object() -> None:
    storage, _, _ = make_storage()
    with pytest.raises(FileNotFoundError):
        storage.read("nope")


def test_read_returns_object() -> None:
    storage, client, _ = make_storage()
    client.bucket_obj.blobs["ok"] = FakeBlob("ok", size=3, data=b"abc")
    obj = storage.read("ok")
    assert (obj.data, obj.generation, obj.gcs_uri) == (b"abc", 7, "gs://docs-bucket/ok")


# --- integrity verification --------------------------------------------------------------------
def _pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _obj(data: bytes) -> StoredObject:
    return StoredObject(
        data=data,
        bucket="b",
        name="uploads/u/d/a.pdf",
        generation=1,
        size=len(data),
        content_type="application/pdf",
        metadata={},
    )


def test_verify_upload_ok_with_checksum() -> None:
    data = _pdf()
    doc = verify_upload(
        _obj(data),
        settings(max_upload_bytes=10_000),
        expected_content_type="application/pdf",
        expected_size=len(data),
        expected_sha256=hashlib.sha256(data).hexdigest().upper(),
        filename="a.pdf",
    )
    assert doc.gcs_uri == "gs://b/uploads/u/d/a.pdf"
    assert doc.page_count == 1


def test_verify_upload_size_mismatch() -> None:
    data = _pdf()
    with pytest.raises(IntegrityError, match="declared"):
        verify_upload(
            _obj(data), settings(max_upload_bytes=10_000),
            expected_content_type="application/pdf", expected_size=len(data) + 1,
        )  # fmt: skip


def test_verify_upload_checksum_mismatch() -> None:
    data = _pdf()
    with pytest.raises(IntegrityError, match="checksum"):
        verify_upload(
            _obj(data), settings(max_upload_bytes=10_000),
            expected_content_type="application/pdf", expected_size=len(data),
            expected_sha256="0" * 64,
        )  # fmt: skip


def test_verify_upload_content_type_spoofing() -> None:
    fake_pdf = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    with pytest.raises(UnsupportedFileTypeError):
        verify_upload(
            _obj(fake_pdf), settings(max_upload_bytes=10_000),
            expected_content_type="application/pdf", expected_size=len(fake_pdf),
        )  # fmt: skip


@pytest.mark.parametrize(
    ("filename", "expected_ascii"),
    [
        ('evil".pdf; filename="x.html', "evil.pdf; filename=x.html"),
        ("line\r\nSet-Cookie: a=b.pdf", "lineSet-Cookie: a=b.pdf"),
        ("reçu café.pdf", "reu caf.pdf"),
        ('\\"', "document"),
    ],
)
def test_content_disposition_cannot_break_out_of_the_header(
    filename: str, expected_ascii: str
) -> None:
    value = content_disposition(filename)
    assert value.startswith(f"inline; filename=\"{expected_ascii}\"; filename*=UTF-8''")
    assert "\r" not in value
    assert "\n" not in value
    encoded = value.split("filename*=UTF-8''", 1)[1]
    assert all(c.isalnum() or c in "%-._~" for c in encoded)


def test_content_disposition_without_filename() -> None:
    assert content_disposition(None) == "inline"


class VersionedBucket(FakeBucket):
    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[tuple[str, int]] = []

    def delete_blob(self, name: str, generation: int | None = None) -> None:
        self.deleted.append((name, generation or 0))


def test_delete_all_versions_deletes_every_generation_of_that_object_only() -> None:
    storage, client, _ = make_storage()
    bucket = VersionedBucket()
    client.bucket_obj = bucket
    storage._bucket = bucket  # type: ignore[assignment]
    versions = []
    for name, gen in [
        ("uploads/u/d/a.pdf", 1),
        ("uploads/u/d/a.pdf", 2),
        ("uploads/u/d/a.pdf.bak", 3),
    ]:
        blob = FakeBlob(name)
        blob.generation = gen
        versions.append(blob)
    calls: list[dict[str, Any]] = []

    def list_blobs(bucket_arg: Any, prefix: str, versions: bool) -> list[FakeBlob]:
        calls.append({"prefix": prefix, "versions": versions})
        return [b for b in all_versions if b.name.startswith(prefix)]

    all_versions = versions
    client.list_blobs = list_blobs  # type: ignore[attr-defined]
    assert storage.delete_all_versions("uploads/u/d/a.pdf") == 2
    assert bucket.deleted == [("uploads/u/d/a.pdf", 1), ("uploads/u/d/a.pdf", 2)]
    assert calls == [{"prefix": "uploads/u/d/a.pdf", "versions": True}]
