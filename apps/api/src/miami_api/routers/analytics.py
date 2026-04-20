from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from miami_common.db import session_app
from miami_domain.schemas import ConfidenceBreakdown, FairValueOut, GradingEvOut

router = APIRouter(tags=["analytics"])


@router.get("/cards/{card_id}/fair-value", response_model=FairValueOut)
def card_fair_value(card_id: int) -> FairValueOut:
    # v1 emits the latest raw-variant feature_snapshot's fair_value_inputs payload.
    with session_app() as s:
        row = (
            s.execute(
                text(
                    """
                SELECT features_json, trailing_cross_source_agreement
                FROM feature_snapshot
                WHERE entity_type='card' AND entity_id=:cid AND subject_variant='raw'
                ORDER BY as_of_date DESC LIMIT 1
                """
                ),
                {"cid": card_id},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail="no_features_yet")
    features = row["features_json"] or {}
    fv = features.get("fair_value_inputs") or {}
    return FairValueOut(
        estimate=None,  # v1 does not yet produce a point estimate
        lower_band=None,
        upper_band=None,
        drivers={k: float(v) for k, v in fv.items() if isinstance(v, (int, float))},
        confidence_label="Medium" if row["trailing_cross_source_agreement"] else "Low",
    )


@router.get("/cards/{card_id}/grading-ev", response_model=GradingEvOut)
def card_grading_ev(card_id: int) -> GradingEvOut:
    with session_app() as s:
        row = (
            s.execute(
                text(
                    """
                SELECT features_json
                FROM feature_snapshot
                WHERE entity_type='card' AND entity_id=:cid AND subject_variant='psa10'
                ORDER BY as_of_date DESC LIMIT 1
                """
                ),
                {"cid": card_id},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail="no_grading_features_yet")
    ev = (row["features_json"] or {}).get("grading_ev_inputs") or {}
    return GradingEvOut(
        ev_per_card=None,
        ev_per_dollar=None,
        p10=ev.get("p10"),
        p9=ev.get("p9"),
        drivers={k: float(v) for k, v in ev.items() if isinstance(v, (int, float))},
        confidence_label="Medium",
    )


@router.get("/cards/{card_id}/confidence", response_model=ConfidenceBreakdown)
def card_confidence(card_id: int) -> ConfidenceBreakdown:
    with session_app() as s:
        row = (
            s.execute(
                text(
                    """
                SELECT confidence_raw, confidence_label, ebay_input_weight,
                       trailing_cross_source_agreement
                FROM mv_latest_scores
                WHERE entity_type='card' AND entity_id=:cid
                LIMIT 1
                """
                ),
                {"cid": card_id},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail="no_scores_yet")
    return ConfidenceBreakdown(
        score=float(row["confidence_raw"]),
        label=row["confidence_label"],
        components={
            "ebay_input_weight": float(row.get("ebay_input_weight") or 0.0),
            "trailing_cross_source_agreement": 1.0
            if row.get("trailing_cross_source_agreement")
            else 0.0,
        },
    )
