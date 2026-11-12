"""Analytics endpoints backed by BigQuery (per-user, per-currency)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Annotated, Any, NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status

from receipt_api.auth import CurrentUser
from receipt_api.deps import AnalyticsDep
from receipt_api.ratelimit import rate_limit
from receipt_api.schemas import AnalyticsOverview, AnalyticsResponse
from receipt_shared.analytics import AnalyticsQueries

router = APIRouter(prefix="/analytics", tags=["analytics"])
User = Annotated[CurrentUser, Depends(rate_limit("analytics"))]

MAX_RANGE_DAYS = 366 * 5
CACHE_TTL_SECONDS = 60.0


class _TTLCache:
    """Tiny per-instance cache: dashboards re-request the same numbers on every view."""

    def __init__(self, ttl: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl, self._clock = ttl, clock
        self._items: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    def get_or_run(
        self, key: tuple[Any, ...], run: Callable[[], list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        now = self._clock()
        with self._lock:
            hit = self._items.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        rows = run()
        with self._lock:
            self._items[key] = (now, rows)
            if len(self._items) > 5000:
                self._items.clear()
        return rows


CACHE = _TTLCache(CACHE_TTL_SECONDS)


class DateRange(NamedTuple):
    """Inclusive days, counted in ``time_zone`` (an IANA name)."""

    start: date
    end: date
    time_zone: str


def date_range(
    start_date: Annotated[
        date | None, Query(description="Default: one year before end_date")
    ] = None,
    end_date: Annotated[date | None, Query(description="Default: today in time_zone")] = None,
    time_zone: Annotated[
        str,
        Query(
            max_length=64,
            description="IANA time zone (e.g. America/Toronto) that defines the days of upload "
            "and review timestamps. Default UTC.",
        ),
    ] = "UTC",
) -> DateRange:
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown time_zone.") from exc
    end = end_date or datetime.now(zone).date()
    start = start_date or end - timedelta(days=365)
    if start > end:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "start_date must be on or before end_date."
        )
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Date range may not exceed 5 years.")
    return DateRange(start, end, time_zone)


Range = Annotated[DateRange, Depends(date_range)]


def _run(
    queries: AnalyticsQueries, name: str, user: CurrentUser, rng: DateRange, limit: int = 10
) -> list[dict[str, Any]]:
    key = (user.uid, name, rng[0], rng[1], rng[2], limit)
    return CACHE.get_or_run(
        key,
        lambda: queries.run(
            name,
            user_id=user.uid,
            start_date=rng[0],
            end_date=rng[1],
            limit=limit,
            time_zone=rng[2],
        ),
    )


@router.get("/overview", response_model=AnalyticsOverview, summary="Dashboard summary")
def overview(user: User, rng: Range, queries: AnalyticsDep) -> AnalyticsOverview:
    names = [
        "total_spending",
        "average_transaction_value",
        "document_type_counts",
        "processing_success_rate",
        "manual_review_rate",
    ]
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        results = dict(
            zip(names, pool.map(lambda n: _run(queries, n, user, rng), names), strict=True)
        )
    return AnalyticsOverview(
        start_date=rng[0],
        end_date=rng[1],
        total_spending=results["total_spending"],
        average_transaction_value=results["average_transaction_value"],
        document_type_counts=results["document_type_counts"],
        processing_success_rate=(results["processing_success_rate"] or [{}])[0],
        manual_review_rate=(results["manual_review_rate"] or [{}])[0],
    )


@router.get("/monthly-spending", response_model=AnalyticsResponse, summary="Spend per month")
def monthly_spending(user: User, rng: Range, queries: AnalyticsDep) -> AnalyticsResponse:
    return AnalyticsResponse(
        start_date=rng[0], end_date=rng[1], rows=_run(queries, "monthly_spending", user, rng)
    )


@router.get("/categories", response_model=AnalyticsResponse, summary="Spend per category")
def categories(user: User, rng: Range, queries: AnalyticsDep) -> AnalyticsResponse:
    return AnalyticsResponse(
        start_date=rng[0], end_date=rng[1], rows=_run(queries, "spending_by_category", user, rng)
    )


@router.get("/merchants", response_model=AnalyticsResponse, summary="Top merchants")
def merchants(
    user: User, rng: Range, queries: AnalyticsDep, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> AnalyticsResponse:
    return AnalyticsResponse(
        start_date=rng[0],
        end_date=rng[1],
        rows=_run(queries, "spending_by_merchant", user, rng, limit),
    )
