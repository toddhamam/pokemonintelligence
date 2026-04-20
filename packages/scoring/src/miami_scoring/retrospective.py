"""Retrospective validation — runs OUTSIDE the live scoring path.

This function looks at forward price movement between `score_snapshot.as_of_date` and
`evaluation_as_of_date`, and writes `retrospective_validation_score` into the
score_snapshot row. Live scoring NEVER reads this column (enforced by AST check).

**Privilege note:** this function uses `session_owner` rather than `session_feature_compute`
on purpose. `miami_feature_compute` is deliberately denied SELECT on raw snapshot tables
to enforce point-in-time safety on the live pipeline — but retrospective validation is
fundamentally a backtest operation that reads raw price history (past `as_of_date`) and
writes to `score_snapshot.retrospective_validation_score`. Running it under the owner
role is the honest expression of "this is not live scoring, this is a backtest."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text

from miami_common.db import session_owner


@dataclass(slots=True)
class RetrospectiveResult:
    scored_rows: int
    updated_rows: int


def retrospective_validate(
    as_of_date: date,
    evaluation_as_of_date: date,
    formula_version: str,
    feature_set_version: str,
    direction_threshold: float = 0.05,
) -> RetrospectiveResult:
    """For each score_snapshot row at `as_of_date`, compute a validation score in
    [-1, 1] based on whether PriceCharting market price moved ≥ threshold in the
    predicted direction between as_of_date and evaluation_as_of_date.
    """
    if evaluation_as_of_date <= as_of_date:
        raise ValueError("evaluation_as_of_date must be strictly after as_of_date")

    scored = 0
    updated = 0
    with session_owner() as s:
        rows = (
            s.execute(
                text(
                    """
                SELECT entity_type, entity_id, subject_variant, breakout_score
                FROM score_snapshot
                WHERE as_of_date = :d
                  AND formula_version = :fv
                  AND feature_set_version = :fsv
                """
                ),
                {"d": as_of_date, "fv": formula_version, "fsv": feature_set_version},
            )
            .mappings()
            .all()
        )

        for row in rows:
            if row["entity_type"] != "card":
                continue  # skip sealed for v1 retrospective
            scored += 1
            # Fetch PriceCharting raw-price movement between as_of and evaluation dates.
            movement = (
                s.execute(
                    text(
                        """
                    WITH
                    baseline AS (
                      SELECT market_price
                      FROM price_snapshot_daily
                      WHERE card_id = :cid
                        AND source = 'pricecharting'
                        AND observed_date <= :d_asof
                      ORDER BY observed_date DESC
                      LIMIT 1
                    ),
                    evaluation AS (
                      SELECT market_price
                      FROM price_snapshot_daily
                      WHERE card_id = :cid
                        AND source = 'pricecharting'
                        AND observed_date <= :d_eval
                      ORDER BY observed_date DESC
                      LIMIT 1
                    )
                    SELECT
                      (SELECT market_price FROM baseline) AS baseline_price,
                      (SELECT market_price FROM evaluation) AS eval_price
                    """
                    ),
                    {
                        "cid": row["entity_id"],
                        "d_asof": as_of_date,
                        "d_eval": evaluation_as_of_date,
                    },
                )
                .mappings()
                .first()
            )
            if movement is None or movement["baseline_price"] in (None, 0):
                continue
            baseline = float(movement["baseline_price"])
            later = float(movement["eval_price"]) if movement["eval_price"] is not None else None
            if later is None:
                continue
            change = (later - baseline) / baseline
            predicted = row["breakout_score"] or 0.0
            predicted_direction = 1 if predicted > 0 else -1 if predicted < 0 else 0
            actual_direction = (
                1 if change >= direction_threshold else -1 if change <= -direction_threshold else 0
            )
            if predicted_direction == 0 or actual_direction == 0:
                validation = 0.0
            elif predicted_direction == actual_direction:
                validation = 1.0
            else:
                validation = -1.0

            s.execute(
                text(
                    """
                    UPDATE score_snapshot
                    SET retrospective_validation_score = :v
                    WHERE as_of_date = :d
                      AND entity_type = :et AND entity_id = :eid
                      AND subject_variant = :sv AND formula_version = :fv
                    """
                ),
                {
                    "v": validation,
                    "d": as_of_date,
                    "et": row["entity_type"],
                    "eid": row["entity_id"],
                    "sv": row["subject_variant"],
                    "fv": formula_version,
                },
            )
            updated += 1
        s.commit()

    return RetrospectiveResult(scored_rows=scored, updated_rows=updated)


def horizon_for(as_of_date: date, horizon_days: int) -> date:
    return as_of_date + timedelta(days=horizon_days)
