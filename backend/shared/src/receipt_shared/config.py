"""Environment-driven configuration shared by every backend service.

All values come from environment variables (or a local ``.env`` file during development).
Nothing project-specific is hardcoded here; defaults are only safe, non-secret values.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Repository root: backend/shared/src/receipt_shared/config.py -> parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


class Settings(BaseSettings):
    """Typed view of the service configuration."""

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # General
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    # Google Cloud
    gcp_project_id: str | None = None
    gcp_region: str = "us-central1"

    # Cloud Storage
    gcs_upload_bucket: str | None = None
    signed_url_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    # Service account that signs upload/download URLs (via IAM signBlob). On Cloud Run this is the
    # API's own account; locally, the developer needs Token Creator on it.
    signing_service_account: str | None = None
    # Documents are sent to Gemini inline (base64) and Vertex AI caps inline request size at
    # ~20 MB, so the default leaves headroom for base64 overhead.
    max_upload_bytes: int = Field(default=15 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=10, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)  # decompression-bomb guard

    # Firestore
    firestore_database: str = "(default)"
    firestore_documents_collection: str = "documents"

    # BigQuery
    bigquery_dataset: str = "receipt_analytics"
    bigquery_location: str = "US"

    # Gemini via Vertex AI
    gemini_model: str = "gemini-3.8-flash"
    gemini_location: str = "global"  # newer Gemini models are served from the global endpoint
    gemini_timeout_seconds: float = Field(default=120.0, gt=0)
    gemini_max_retries: int = Field(default=4, ge=0)
    gemini_retry_initial_delay_seconds: float = Field(default=1.0, ge=0)
    gemini_retry_max_delay_seconds: float = Field(default=30.0, ge=0)
    gemini_max_output_tokens: int = Field(default=8192, gt=0)
    # None = model default. 0 disables thinking on models that allow it (lower latency/cost).
    gemini_thinking_budget: int | None = None

    # Worker
    # How long a processing claim is held; a crashed attempt can be retaken after it expires.
    worker_lease_seconds: int = Field(default=360, ge=30)
    # Transient failures (Gemini 5xx/429/timeouts) are retried by Eventarc up to this many times.
    max_processing_attempts: int = Field(default=5, ge=1)

    # Validation
    # Absolute tolerance for subtotal/tax/discount vs. total (at least one currency minor unit).
    money_tolerance: Decimal = Field(default=Decimal("0.02"), ge=0)
    # Tolerance when comparing the sum of line items with the document totals.
    line_item_tolerance: Decimal = Field(default=Decimal("0.05"), ge=0)
    future_date_tolerance_days: int = Field(default=1, ge=0)  # clock skew / time zones
    max_document_age_days: int = Field(default=3650, gt=0)  # older dates are flagged, not rejected
    max_reasonable_amount: Decimal = Field(default=Decimal("1000000"), gt=0)  # larger is flagged
    supported_currencies: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "USD",
            "CAD",
            "EUR",
            "GBP",
            "AUD",
            "INR",
            "JPY",
            "CHF",
            "MXN",
            "NZD",
            "SGD",
            "PKR",
        ]
    )

    # Auth
    firebase_project_id: str | None = None

    # API
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("supported_currencies", mode="before")
    @classmethod
    def _parse_currencies(cls, value: object) -> object:
        if isinstance(value, str):
            return [c.strip().upper() for c in value.split(",") if c.strip()]
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @field_validator(
        "gcp_project_id",
        "gcs_upload_bucket",
        "signing_service_account",
        "firebase_project_id",
        "gemini_thinking_budget",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log level: {value}")
        return level

    @property
    def effective_firebase_project_id(self) -> str | None:
        return self.firebase_project_id or self.gcp_project_id


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (cached; call ``get_settings.cache_clear()`` in tests)."""
    return Settings()
