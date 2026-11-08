from decimal import Decimal

import pytest

from receipt_shared.config import Environment, Settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key in ("GCP_PROJECT_ID", "SUPPORTED_CURRENCIES", "CORS_ALLOWED_ORIGINS", "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_defaults_have_no_project(clean_env: pytest.MonkeyPatch) -> None:
    s = Settings(_env_file=None)
    assert s.gcp_project_id is None
    assert s.environment is Environment.LOCAL
    assert s.money_tolerance == Decimal("0.02")


def test_reads_environment(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GCP_PROJECT_ID", "my-project")
    clean_env.setenv("ENVIRONMENT", "dev")
    clean_env.setenv("SUPPORTED_CURRENCIES", "usd, eur ,")
    clean_env.setenv("CORS_ALLOWED_ORIGINS", "http://a.test,https://b.test")
    s = Settings(_env_file=None)
    assert s.gcp_project_id == "my-project"
    assert s.environment is Environment.DEV
    assert s.supported_currencies == ["USD", "EUR"]
    assert s.cors_allowed_origins == ["http://a.test", "https://b.test"]


def test_empty_strings_become_none(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GCP_PROJECT_ID", "  ")
    assert Settings(_env_file=None).gcp_project_id is None


def test_firebase_project_falls_back_to_gcp_project(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GCP_PROJECT_ID", "p1")
    clean_env.delenv("FIREBASE_PROJECT_ID", raising=False)
    assert Settings(_env_file=None).effective_firebase_project_id == "p1"


def test_invalid_log_level_rejected(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("LOG_LEVEL", "loud")
    with pytest.raises(ValueError, match="invalid log level"):
        Settings(_env_file=None)
