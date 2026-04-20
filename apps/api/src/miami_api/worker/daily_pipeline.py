"""daily_pipeline — runs the full daily ingestion → features → scores → invalidation chain.

1. collectors (PriceCharting raw, PriceCharting graded, Pokémon TCG, eBay, PSA, Pokemon Center)
2. build_features(today)
3. score() for each feature_snapshot row → score_snapshot row
4. refresh mv_latest_prices, mv_latest_scores
5. POST /api/revalidate with tags ["scores:{today}", "rankings:breakouts", ...]

Invoked by:
- CLI: `python -m miami_api.worker.daily_pipeline`
- HTTP: `POST /worker/daily` on the FastAPI app (protected by service token)
"""

from __future__ import annotations

import json
from datetime import date

import httpx
from sqlalchemy import text

from miami_collectors.ebay import EbayCollector
from miami_collectors.pokemon_center import PokemonCenterStockCollector
from miami_collectors.pokemontcg import PokemonTcgCollector
from miami_collectors.pricecharting import (
    PriceChartingGradedCollector,
    PriceChartingRawCollector,
)
from miami_collectors.psa import PsaPopulationCollector
from miami_common.db import session_feature_compute, session_owner
from miami_common.logging import configure_logging, get_logger
from miami_common.settings import get_settings
from miami_common.time import today_utc
from miami_features import FEATURE_SET_VERSION, build_features
from miami_scoring import load_active_formulas, score

configure_logging()
log = get_logger(__name__)


def run(as_of_date: date | None = None) -> dict[str, object]:
    d = as_of_date or today_utc()
    log.info("daily_pipeline_start", as_of_date=str(d))

    # ---- 1. ingest ----
    collectors = [
        PriceChartingRawCollector(),
        PriceChartingGradedCollector(),
        PokemonTcgCollector(),
        EbayCollector(),
        PsaPopulationCollector(),
        PokemonCenterStockCollector(),
    ]
    ingest_results: list[dict[str, object]] = []
    for c in collectors:
        result = c.run(d)
        ingest_results.append(
            {"source": c.source, "status": result.status, "rows_out": result.rows_out}
        )
        if result.status != "success":
            log.warning("collector_non_success", source=c.source, error=result.error)

    # ---- 2. build features ----
    feature_rows = build_features(d, FEATURE_SET_VERSION)
    log.info("features_built", count=len(feature_rows))

    # ---- 3. score ----
    formulas = load_active_formulas()
    scored_count = 0
    with session_feature_compute() as s:
        feature_records = (
            s.execute(
                text(
                    """
                SELECT entity_type, entity_id, subject_variant, features_json,
                       ebay_input_weight, trailing_cross_source_agreement
                FROM feature_snapshot
                WHERE as_of_date = :d AND feature_set_version = :v
                """
                ),
                {"d": d, "v": FEATURE_SET_VERSION},
            )
            .mappings()
            .all()
        )

        for fr in feature_records:
            features = dict(fr["features_json"])
            features["ebay_input_weight"] = float(fr["ebay_input_weight"])
            features["trailing_cross_source_agreement"] = bool(
                fr["trailing_cross_source_agreement"]
            )
            output = score(features, formulas)
            s.execute(
                text(
                    """
                    INSERT INTO score_snapshot (
                        entity_type, entity_id, subject_variant, as_of_date,
                        formula_version, feature_set_version, inputs_hash,
                        breakout_score, arbitrage_score, long_term_score,
                        confidence_raw, confidence_label,
                        ebay_input_weight, trailing_cross_source_agreement,
                        recommendation_label, explanations
                    ) VALUES (
                        :et, :eid, :sv, :d, :fv, :fsv, :ih,
                        :bs, :as_, :lts,
                        :cr, :cl,
                        :eiw, :tcs,
                        :rl, CAST(:ex AS JSONB)
                    )
                    ON CONFLICT
                      (as_of_date, entity_type, entity_id, subject_variant, formula_version)
                    DO UPDATE SET
                      feature_set_version = EXCLUDED.feature_set_version,
                      inputs_hash = EXCLUDED.inputs_hash,
                      breakout_score = EXCLUDED.breakout_score,
                      arbitrage_score = EXCLUDED.arbitrage_score,
                      long_term_score = EXCLUDED.long_term_score,
                      confidence_raw = EXCLUDED.confidence_raw,
                      confidence_label = EXCLUDED.confidence_label,
                      ebay_input_weight = EXCLUDED.ebay_input_weight,
                      trailing_cross_source_agreement = EXCLUDED.trailing_cross_source_agreement,
                      recommendation_label = EXCLUDED.recommendation_label,
                      explanations = EXCLUDED.explanations,
                      computed_at = now()
                    """
                ),
                {
                    "et": fr["entity_type"],
                    "eid": fr["entity_id"],
                    "sv": fr["subject_variant"],
                    "d": d,
                    "fv": formulas.breakout.version,
                    "fsv": FEATURE_SET_VERSION,
                    "ih": output.inputs_hash,
                    "bs": output.breakout_score,
                    "as_": output.arbitrage_score,
                    "lts": output.long_term_score,
                    "cr": output.confidence_raw,
                    "cl": output.confidence_label,
                    "eiw": output.ebay_input_weight,
                    "tcs": output.trailing_cross_source_agreement,
                    "rl": output.recommendation_label,
                    "ex": json.dumps(output.explanations),
                },
            )
            scored_count += 1
        s.commit()

    # ---- 4. refresh materialized views (requires owner) ----
    with session_owner() as s:
        s.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_prices"))
        s.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_scores"))
        s.commit()
    log.info("views_refreshed")

    # ---- 5. invalidate Next.js cache via protected route ----
    _invalidate_web_cache(d)

    log.info("daily_pipeline_complete", scored=scored_count, ingest=ingest_results)
    return {"as_of_date": str(d), "scored": scored_count, "ingest": ingest_results}


def _invalidate_web_cache(d: date) -> None:
    settings = get_settings()
    url = f"{settings.next_public_api_url.rstrip('/')}/api/revalidate"
    # The revalidate route lives on Next.js, not on this API. In dev we call localhost:3000.
    web_url = url.replace(":8000", ":3000").replace("/api/revalidate", "/api/revalidate")
    try:
        httpx.post(
            web_url,
            json={
                "tags": [
                    f"scores:{d.isoformat()}",
                    "rankings:breakouts",
                    "rankings:arbitrage",
                    "rankings:long_term",
                ]
            },
            headers={"Authorization": f"Bearer {settings.pipeline_revalidate_token}"},
            timeout=10.0,
        )
    except Exception as exc:
        log.warning("revalidate_failed", error=repr(exc))


if __name__ == "__main__":
    run()
