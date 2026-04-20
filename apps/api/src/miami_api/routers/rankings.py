from __future__ import annotations

from fastapi import APIRouter, Query, Response
from sqlalchemy import text

from miami_common.db import session_app
from miami_domain.schemas import Page, RankingRow, ScoresBlock

router = APIRouter(tags=["rankings"])

_LABEL_RANK = {"High": 3, "Medium": 2, "Low": 1, "Experimental": 0}


def _apply_cache_tag(response: Response, tag: str) -> None:
    # Emitted so Next.js Cache Components can invalidate this tag via revalidateTag().
    existing = response.headers.get("Cache-Tag", "")
    merged = ",".join(filter(None, [existing, tag]))
    response.headers["Cache-Tag"] = merged


def _score_query(order_column: str, direction: str = "DESC") -> str:
    """Rankings all use the same shape — just swap the ORDER BY column."""
    return f"""
        SELECT
          s.entity_type, s.entity_id, s.subject_variant, s.as_of_date,
          s.breakout_score, s.arbitrage_score, s.long_term_score,
          s.confidence_raw, s.confidence_label, s.recommendation_label,
          s.explanations,
          COALESCE(c.name, sp.product_name) AS name,
          COALESCE(cs.name, sps.name) AS set_name
        FROM mv_latest_scores s
        LEFT JOIN card c ON s.entity_type = 'card' AND s.entity_id = c.id
        LEFT JOIN set cs ON cs.id = c.set_id
        LEFT JOIN sealed_product sp ON s.entity_type = 'sealed_product' AND s.entity_id = sp.id
        LEFT JOIN set sps ON sps.id = sp.set_id
        WHERE (:min_confidence IS NULL OR s.confidence_raw >= :min_confidence)
          AND {order_column} IS NOT NULL
        ORDER BY {order_column} {direction}
        LIMIT :limit
    """


def _row_to_ranking(row: dict) -> RankingRow:
    explanations = row.get("explanations") or []
    if isinstance(explanations, dict):
        # jsonb could come back as a dict if someone wrote it that way; normalize.
        explanations = list(explanations.get("items") or [])
    return RankingRow(
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        subject_variant=row["subject_variant"],
        name=row.get("name") or f"{row['entity_type']}:{row['entity_id']}",
        set_name=row.get("set_name"),
        scores=ScoresBlock(
            breakout=row.get("breakout_score"),
            arbitrage=row.get("arbitrage_score"),
            long_term=row.get("long_term_score"),
            confidence_raw=float(row["confidence_raw"]),
            confidence_label=row["confidence_label"],
            label=row.get("recommendation_label"),
        ),
        snapshot_date=row["as_of_date"],
        explanations=explanations if isinstance(explanations, list) else [],
    )


@router.get("/rankings/breakouts", response_model=Page[RankingRow])
def rankings_breakouts(
    response: Response,
    min_confidence: float | None = Query(default=0.55, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[RankingRow]:
    _apply_cache_tag(response, "rankings:breakouts")
    with session_app() as s:
        rows = (
            s.execute(
                text(_score_query("s.breakout_score")),
                {"min_confidence": min_confidence, "limit": limit},
            )
            .mappings()
            .all()
        )
    return Page[RankingRow](items=[_row_to_ranking(dict(r)) for r in rows])


@router.get("/rankings/arbitrage", response_model=Page[RankingRow])
def rankings_arbitrage(
    response: Response,
    min_confidence: float | None = Query(default=0.55, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[RankingRow]:
    _apply_cache_tag(response, "rankings:arbitrage")
    with session_app() as s:
        rows = (
            s.execute(
                text(_score_query("s.arbitrage_score")),
                {"min_confidence": min_confidence, "limit": limit},
            )
            .mappings()
            .all()
        )
    return Page[RankingRow](items=[_row_to_ranking(dict(r)) for r in rows])


@router.get("/rankings/long-term", response_model=Page[RankingRow])
def rankings_long_term(
    response: Response,
    min_confidence: float | None = Query(default=0.55, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[RankingRow]:
    _apply_cache_tag(response, "rankings:long_term")
    with session_app() as s:
        rows = (
            s.execute(
                text(_score_query("s.long_term_score")),
                {"min_confidence": min_confidence, "limit": limit},
            )
            .mappings()
            .all()
        )
    return Page[RankingRow](items=[_row_to_ranking(dict(r)) for r in rows])
