from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import version

from fastapi import APIRouter

from receipt_shared.config import get_settings
from receipt_shared.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service="api",
        version=version("receipt-api"),
        environment=settings.environment.value,
        timestamp=datetime.now(UTC),
    )
