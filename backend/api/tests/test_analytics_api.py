from datetime import date

import pytest

from receipt_api.ratelimit import LIMITERS, TokenBucketLimiter

from .conftest import Env


def test_overview_combines_queries_for_the_signed_in_user(env: Env) -> None:
    resp = env.get(
        "/analytics/overview", params={"start_date": "2026-01-01", "end_date": "2026-12-31"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["processing_success_rate"] == {"processed_documents": 3, "success_rate": 1.0}
    assert body["manual_review_rate"] == {"review_rate": 0.5}
    assert body["total_spending"] == [{"query": "total_spending", "user_id": "user_A"}]
    assert {c["name"] for c in env.queries.calls} == {
        "total_spending",
        "average_transaction_value",
        "document_type_counts",
        "processing_success_rate",
        "manual_review_rate",
    }
    assert all(c["user_id"] == "user_A" for c in env.queries.calls)
    assert all(c["start_date"] == date(2026, 1, 1) for c in env.queries.calls)


@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/analytics/monthly-spending", "monthly_spending"),
        ("/analytics/categories", "spending_by_category"),
        ("/analytics/merchants", "spending_by_merchant"),
    ],
)
def test_individual_endpoints(env: Env, path: str, query: str) -> None:
    body = env.get(path).json()
    assert body["rows"] == [{"query": query, "user_id": "user_A"}]
    assert body["end_date"] >= body["start_date"]


def test_results_are_cached_per_user(env: Env) -> None:
    env.get("/analytics/categories")
    env.get("/analytics/categories")
    env.get("/analytics/categories", token="token-b")
    assert [c["user_id"] for c in env.queries.calls] == ["user_A", "user_B"]


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2026-12-31", "end_date": "2026-01-01"},
        {"start_date": "2000-01-01", "end_date": "2026-01-01"},
    ],
)
def test_invalid_ranges(env: Env, params: dict[str, str]) -> None:
    assert env.get("/analytics/overview", params=params).status_code == 400


def test_merchant_limit_bounds(env: Env) -> None:
    assert env.get("/analytics/merchants", params={"limit": 0}).status_code == 422
    assert env.get("/analytics/merchants", params={"limit": 51}).status_code == 422
    env.get("/analytics/merchants", params={"limit": 5})
    assert env.queries.calls[-1]["limit"] == 5


def test_rate_limit_returns_429_with_retry_after(env: Env) -> None:
    LIMITERS["analytics"] = TokenBucketLimiter(2)
    codes = [
        env.get("/analytics/categories", params={"start_date": f"2026-01-0{i}"}).status_code
        for i in range(1, 4)
    ]
    assert codes == [200, 200, 429]
    resp = env.get("/analytics/categories")
    assert resp.json()["error"]["code"] == "rate_limited"
    assert int(resp.headers["Retry-After"]) >= 1
    # Limits are per user.
    assert env.get("/analytics/categories", token="token-b").status_code == 200


def test_token_bucket_refills() -> None:
    now = [0.0]
    limiter = TokenBucketLimiter(60, clock=lambda: now[0])  # 1 per second
    assert all(limiter.acquire("u") == 0 for _ in range(60))
    assert limiter.acquire("u") > 0
    now[0] += 1.0
    assert limiter.acquire("u") == 0


def test_time_zone_is_passed_to_every_query(env: Env) -> None:
    resp = env.get(
        "/analytics/overview",
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-11-11",
            "time_zone": "America/Halifax",
        },
    )
    assert resp.status_code == 200
    assert {c["time_zone"] for c in env.queries.calls} == {"America/Halifax"}


def test_time_zone_defaults_to_utc_and_rejects_unknown_zones(env: Env) -> None:
    assert env.get("/analytics/categories").status_code == 200
    assert env.queries.calls[-1]["time_zone"] == "UTC"
    for bad in ("Mars/Olympus", "../../etc/passwd", "x" * 65):
        resp = env.get("/analytics/categories", params={"time_zone": bad})
        assert resp.status_code in (400, 422), bad
