"""CloudEvents (HTTP binding) parsing for Cloud Storage events delivered by Eventarc.

Eventarc uses *binary* content mode (attributes in ``ce-*`` headers, ``data`` as the JSON body);
*structured* mode (``application/cloudevents+json``) is accepted too.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

FINALIZED = "google.cloud.storage.object.v1.finalized"


class InvalidEventError(ValueError):
    pass


@dataclass(frozen=True)
class StorageObjectEvent:
    id: str
    type: str
    source: str
    bucket: str
    name: str
    generation: int
    size: int | None
    content_type: str | None


def _int(value: Any, field: str, *, required: bool) -> int | None:
    if value is None or value == "":
        if required:
            raise InvalidEventError(f"missing {field}")
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidEventError(f"invalid {field}") from exc


def parse_storage_event(headers: Mapping[str, str], body: bytes) -> StorageObjectEvent:
    lower = {k.lower(): v for k, v in headers.items()}
    try:
        payload = json.loads(body or b"null")
    except json.JSONDecodeError as exc:
        raise InvalidEventError("body is not JSON") from exc

    if lower.get("content-type", "").startswith("application/cloudevents+json"):
        if not isinstance(payload, dict):
            raise InvalidEventError("structured event is not an object")
        attrs = {k: payload.get(k) for k in ("id", "type", "source")}
        data = payload.get("data")
    else:
        attrs = {k: lower.get(f"ce-{k}") for k in ("id", "type", "source")}
        data = payload

    if not all(isinstance(attrs[k], str) and attrs[k] for k in attrs):
        raise InvalidEventError("missing CloudEvents attributes (id, type, source)")
    if not isinstance(data, dict):
        raise InvalidEventError("event data is not an object")
    bucket, name = data.get("bucket"), data.get("name")
    if not isinstance(bucket, str) or not isinstance(name, str) or not bucket or not name:
        raise InvalidEventError("event data has no bucket/name")

    generation = _int(data.get("generation"), "generation", required=True)
    if generation is None:  # pragma: no cover - required=True raises instead
        raise InvalidEventError("missing generation")
    return StorageObjectEvent(
        id=str(attrs["id"]),
        type=str(attrs["type"]),
        source=str(attrs["source"]),
        bucket=bucket,
        name=name,
        generation=generation,
        size=_int(data.get("size"), "size", required=False),
        content_type=data.get("contentType") if isinstance(data.get("contentType"), str) else None,
    )
