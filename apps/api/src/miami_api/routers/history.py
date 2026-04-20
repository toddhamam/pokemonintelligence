from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import text

from miami_common.db import session_app
from miami_domain.schemas import PopulationPoint, PricePoint

router = APIRouter(tags=["history"])

_DEFAULT_LOOKBACK_DAYS = 90


def _default_from(from_date: date | None) -> date:
    return from_date or (date.today() - timedelta(days=_DEFAULT_LOOKBACK_DAYS))


@router.get("/cards/{card_id}/price-history", response_model=list[PricePoint])
def card_price_history(
    card_id: int,
    source: str | None = Query(default=None),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> list[PricePoint]:
    # CAST(:source AS TEXT) is required — without it Postgres cannot infer the
    # type of a NULL-valued parameter inside `:source IS NULL OR ...`.
    sql = """
        SELECT observed_date, source, market_price, low_price, high_price, confidence
        FROM price_snapshot_daily
        WHERE card_id = :cid
          AND observed_date >= :from_d
          AND observed_date <= :to_d
          AND (CAST(:source AS TEXT) IS NULL OR source = CAST(:source AS TEXT))
        ORDER BY observed_date ASC, source ASC
    """
    with session_app() as s:
        rows = (
            s.execute(
                text(sql),
                {
                    "cid": card_id,
                    "from_d": _default_from(from_date),
                    "to_d": to_date or date.today(),
                    "source": source,
                },
            )
            .mappings()
            .all()
        )
    return [PricePoint(**dict(r)) for r in rows]


@router.get("/cards/{card_id}/population-history", response_model=list[PopulationPoint])
def card_population_history(
    card_id: int,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> list[PopulationPoint]:
    with session_app() as s:
        rows = (
            s.execute(
                text(
                    """
                SELECT observed_date, grade_company, total_population,
                       grade_10_population, grade_9_population
                FROM population_snapshot
                WHERE card_id = :cid
                  AND observed_date >= :from_d
                  AND observed_date <= :to_d
                ORDER BY observed_date ASC
                """
                ),
                {
                    "cid": card_id,
                    "from_d": _default_from(from_date),
                    "to_d": to_date or date.today(),
                },
            )
            .mappings()
            .all()
        )
    return [PopulationPoint(**dict(r)) for r in rows]


@router.get("/sealed-products/{product_id}/price-history", response_model=list[PricePoint])
def sealed_price_history(
    product_id: int,
    source: str | None = Query(default=None),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> list[PricePoint]:
    with session_app() as s:
        rows = (
            s.execute(
                text(
                    """
                SELECT observed_date, source, market_price, low_price, high_price, confidence
                FROM sealed_snapshot_daily
                WHERE sealed_product_id = :pid
                  AND observed_date >= :from_d
                  AND observed_date <= :to_d
                  AND (CAST(:source AS TEXT) IS NULL OR source = CAST(:source AS TEXT))
                ORDER BY observed_date ASC, source ASC
                """
                ),
                {
                    "pid": product_id,
                    "from_d": _default_from(from_date),
                    "to_d": to_date or date.today(),
                    "source": source,
                },
            )
            .mappings()
            .all()
        )
    return [PricePoint(**dict(r)) for r in rows]
