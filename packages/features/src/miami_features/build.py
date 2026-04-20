"""build_features — pure function that recomputes features for every entity at as_of_date.

Reads only via *_asof() functions (see miami_features.as_of). Produces one row per
(entity_type, entity_id, subject_variant, as_of_date, feature_set_version).

Core feature families (v1):
- Trailing price momentum (7/14/30d) from PriceCharting + Pokémon TCG
- Trailing listing-flow features (demand pressure, replenishment, depletion)
- Grading EV inputs (p10, p9 from PSA population snapshots; price ratio from graded snapshots)
- Fair-value inputs (placeholder defaults in v1; elasticity regression in v2)
- Pair-wise cross-source agreement flag for confidence

Writes are bulk upserts into `feature_snapshot` under the feature_compute role.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import polars as pl
from sqlalchemy import text

from miami_common.db import session_feature_compute
from miami_common.logging import get_logger
from miami_features import as_of as asof

log = get_logger(__name__)


@dataclass(slots=True)
class FeatureRow:
    entity_type: str
    entity_id: int
    subject_variant: str
    as_of_date: date
    feature_set_version: str
    features_json: dict[str, Any]
    ebay_input_weight: float
    trailing_cross_source_agreement: bool


def build_features(as_of_date: date, feature_set_version: str = "1.0.0") -> list[FeatureRow]:
    """Compute features for every tracked entity/subject_variant at as_of_date.

    PIT discipline:
    - All snapshot reads go through `*_asof(as_of_date)`, which filters by
      `observed_date <= as_of_date AND ingested_at <= as_of_date + 12 hours`.
    - Trailing windows are computed by slicing the as-of dataframe by `observed_date`.
    - The function NEVER reads `score_snapshot.retrospective_validation_score` or any
      column that would require data observed after `as_of_date`.
    """
    prices_df = asof.price_snapshot_asof(as_of_date)
    graded_df = asof.graded_snapshot_asof(as_of_date)
    sealed_df = asof.sealed_snapshot_asof(as_of_date)
    flow_df = asof.listing_flow_asof(as_of_date)
    pop_df = asof.population_snapshot_asof(as_of_date)

    rows: list[FeatureRow] = []

    # ---- Raw card features (one row per card) ----
    card_ids = _unique_card_ids(prices_df)
    for card_id in card_ids:
        card_prices = _filter_card(prices_df, card_id)
        if card_prices.is_empty():
            continue
        momentum = _trailing_momentum(card_prices, as_of_date)
        sources = sorted({s for s in card_prices["source"].to_list()})
        agreement = _trailing_cross_source_agreement(card_prices, as_of_date)
        ebay_weight = _ebay_weight_for(flow_df, "card", card_id, "raw")
        feature_payload = {
            **momentum,
            "sources_present": sources,
            "latest_market_price": _latest_price(card_prices),
            "listing_flow": _listing_flow_features(flow_df, "card", card_id, "raw"),
            "fair_value_inputs": _fair_value_defaults(),
        }
        rows.append(
            FeatureRow(
                entity_type="card",
                entity_id=card_id,
                subject_variant="raw",
                as_of_date=as_of_date,
                feature_set_version=feature_set_version,
                features_json=feature_payload,
                ebay_input_weight=ebay_weight,
                trailing_cross_source_agreement=agreement,
            )
        )

    # ---- Graded (PSA 9 / PSA 10) ----
    graded_card_ids = _unique_card_ids(graded_df)
    for card_id in graded_card_ids:
        for grade, variant in (("9", "psa9"), ("10", "psa10")):
            subset = _filter_graded(graded_df, card_id, grade)
            if subset.is_empty():
                continue
            momentum = _trailing_momentum(subset, as_of_date)
            ebay_weight = _ebay_weight_for(flow_df, "card", card_id, variant)
            grading_ev = _grading_ev_features(card_id, pop_df, subset)
            feature_payload = {
                **momentum,
                "latest_market_price": _latest_price(subset),
                "listing_flow": _listing_flow_features(flow_df, "card", card_id, variant),
                "grading_ev_inputs": grading_ev,
            }
            rows.append(
                FeatureRow(
                    entity_type="card",
                    entity_id=card_id,
                    subject_variant=variant,
                    as_of_date=as_of_date,
                    feature_set_version=feature_set_version,
                    features_json=feature_payload,
                    ebay_input_weight=ebay_weight,
                    trailing_cross_source_agreement=_trailing_cross_source_agreement(
                        subset, as_of_date
                    ),
                )
            )

    # ---- Sealed products ----
    if not sealed_df.is_empty():
        sealed_ids = sorted({int(x) for x in sealed_df["sealed_product_id"].to_list()})
        for sp_id in sealed_ids:
            subset = sealed_df.filter(pl.col("sealed_product_id") == sp_id)
            if subset.is_empty():
                continue
            momentum = _trailing_momentum(subset, as_of_date)
            ebay_weight = _ebay_weight_for(flow_df, "sealed_product", sp_id, "sealed")
            feature_payload = {
                **momentum,
                "latest_market_price": _latest_price(subset),
                "listing_flow": _listing_flow_features(flow_df, "sealed_product", sp_id, "sealed"),
                "long_term_inputs": {"reprint_risk_score": 0.5},  # v1 placeholder
            }
            rows.append(
                FeatureRow(
                    entity_type="sealed_product",
                    entity_id=sp_id,
                    subject_variant="sealed",
                    as_of_date=as_of_date,
                    feature_set_version=feature_set_version,
                    features_json=feature_payload,
                    ebay_input_weight=ebay_weight,
                    trailing_cross_source_agreement=_trailing_cross_source_agreement(
                        subset, as_of_date
                    ),
                )
            )

    _persist(rows)
    log.info("build_features_complete", as_of_date=str(as_of_date), rows=len(rows))
    return rows


# ---------- helpers ----------


def _unique_card_ids(df: pl.DataFrame) -> list[int]:
    if df.is_empty() or "card_id" not in df.columns:
        return []
    return sorted({int(x) for x in df["card_id"].to_list()})


def _filter_card(df: pl.DataFrame, card_id: int) -> pl.DataFrame:
    return df.filter(pl.col("card_id") == card_id) if not df.is_empty() else df


def _filter_graded(df: pl.DataFrame, card_id: int, grade: str) -> pl.DataFrame:
    if df.is_empty():
        return df
    return df.filter(
        (pl.col("card_id") == card_id)
        & (pl.col("grade_company") == "PSA")
        & (pl.col("grade") == grade)
    )


def _latest_price(df: pl.DataFrame) -> float | None:
    if df.is_empty():
        return None
    latest = df.sort("observed_date", descending=True).row(0, named=True)
    return float(latest["market_price"]) if latest["market_price"] is not None else None


def _trailing_momentum(df: pl.DataFrame, as_of_date: date) -> dict[str, float | None]:
    if df.is_empty():
        return {"momentum_7d": None, "momentum_14d": None, "momentum_30d": None}
    ordered = df.sort("observed_date")
    out: dict[str, float | None] = {}
    for days, label in ((7, "momentum_7d"), (14, "momentum_14d"), (30, "momentum_30d")):
        start = as_of_date - timedelta(days=days)
        window = ordered.filter(pl.col("observed_date") >= start)
        if window.height < 2:
            out[label] = None
            continue
        first_price = window["market_price"].to_list()[0]
        last_price = window["market_price"].to_list()[-1]
        if first_price is None or last_price is None or float(first_price) == 0:
            out[label] = None
            continue
        out[label] = (float(last_price) - float(first_price)) / float(first_price)
    return out


def _trailing_cross_source_agreement(df: pl.DataFrame, as_of_date: date) -> bool:
    """True when trailing 14d direction agrees across distinct sources. Trailing only."""
    if df.is_empty() or "source" not in df.columns:
        return False
    start = as_of_date - timedelta(days=14)
    window = df.filter(pl.col("observed_date") >= start)
    sources = sorted({s for s in window["source"].to_list()})
    if len(sources) < 2:
        return False
    directions: list[int] = []
    for src in sources:
        sub = window.filter(pl.col("source") == src).sort("observed_date")
        prices = [p for p in sub["market_price"].to_list() if p is not None]
        if len(prices) < 2:
            continue
        delta = float(prices[-1]) - float(prices[0])
        directions.append(1 if delta > 0 else -1 if delta < 0 else 0)
    if len(directions) < 2:
        return False
    return all(d == directions[0] and d != 0 for d in directions)


def _ebay_weight_for(
    flow_df: pl.DataFrame, entity_type: str, entity_id: int, subject_variant: str
) -> float:
    if flow_df.is_empty():
        return 0.0
    sub = flow_df.filter(
        (pl.col("entity_type") == entity_type)
        & (pl.col("entity_id") == entity_id)
        & (pl.col("subject_variant") == subject_variant)
    )
    if sub.is_empty():
        return 0.0
    active = int(sub.sort("observed_date", descending=True).row(0, named=True)["active_listings"])
    # v1 heuristic: any eBay observation pushes ebay_input_weight to 0.5; heavy flow → 0.7.
    if active >= 20:
        return 0.7
    if active > 0:
        return 0.5
    return 0.0


def _listing_flow_features(
    flow_df: pl.DataFrame, entity_type: str, entity_id: int, subject_variant: str
) -> dict[str, float | None]:
    if flow_df.is_empty():
        return {
            "active_listings": None,
            "new_listings": None,
            "estimated_disappeared_count": None,
            "data_quality_score": None,
        }
    sub = flow_df.filter(
        (pl.col("entity_type") == entity_type)
        & (pl.col("entity_id") == entity_id)
        & (pl.col("subject_variant") == subject_variant)
    )
    if sub.is_empty():
        return {
            "active_listings": None,
            "new_listings": None,
            "estimated_disappeared_count": None,
            "data_quality_score": None,
        }
    latest = sub.sort("observed_date", descending=True).row(0, named=True)
    return {
        "active_listings": int(latest["active_listings"]),
        "new_listings": int(latest["new_listings"]),
        "estimated_disappeared_count": int(latest["estimated_disappeared_count"]),
        "data_quality_score": float(latest["data_quality_score"]),
    }


def _grading_ev_features(
    card_id: int, pop_df: pl.DataFrame, graded_subset: pl.DataFrame
) -> dict[str, float | None]:
    if pop_df.is_empty():
        return {"p10": None, "p9": None, "population_growth_penalty": None}
    sub = pop_df.filter(pl.col("card_id") == card_id).sort("observed_date", descending=True)
    if sub.is_empty():
        return {"p10": None, "p9": None, "population_growth_penalty": None}
    latest = sub.row(0, named=True)
    total = int(latest["total_population"])
    if total == 0:
        return {"p10": None, "p9": None, "population_growth_penalty": None}
    return {
        "p10": int(latest["grade_10_population"]) / total,
        "p9": int(latest["grade_9_population"]) / total,
        "population_growth_penalty": 0.0,  # v1 placeholder
    }


def _fair_value_defaults() -> dict[str, float]:
    return {
        "pull_cost_score": 0.5,
        "desirability_score": 0.5,
        "rarity_slot_crowding": 0.5,
        "character_premium_score": 0.5,
    }


def _persist(rows: list[FeatureRow]) -> None:
    if not rows:
        return
    with session_feature_compute() as s:
        for r in rows:
            s.execute(
                text(
                    """
                    INSERT INTO feature_snapshot (
                        entity_type, entity_id, subject_variant, as_of_date,
                        feature_set_version, features_json, ebay_input_weight,
                        trailing_cross_source_agreement, computed_at
                    ) VALUES (
                        :entity_type, :entity_id, :subject_variant, :as_of_date,
                        :feature_set_version, CAST(:features AS JSONB), :ebay_input_weight,
                        :agreement, now()
                    )
                    ON CONFLICT
                      (as_of_date, entity_type, entity_id, subject_variant, feature_set_version)
                    DO UPDATE SET
                      features_json = EXCLUDED.features_json,
                      ebay_input_weight = EXCLUDED.ebay_input_weight,
                      trailing_cross_source_agreement = EXCLUDED.trailing_cross_source_agreement,
                      computed_at = now()
                    """
                ),
                {
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "subject_variant": r.subject_variant,
                    "as_of_date": r.as_of_date,
                    "feature_set_version": r.feature_set_version,
                    "features": json.dumps(r.features_json, default=str),
                    "ebay_input_weight": r.ebay_input_weight,
                    "agreement": r.trailing_cross_source_agreement,
                },
            )
        s.commit()
