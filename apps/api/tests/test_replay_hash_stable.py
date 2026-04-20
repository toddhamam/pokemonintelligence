"""Replay hash stability. Given a pinned feature vector + HEAD formulas, score() output
must be bit-stable across commits. A regression here means someone changed scoring
behavior without bumping formula_version — a serious compliance issue for backtests.
"""

import json
from dataclasses import asdict

from miami_scoring import load_active_formulas, score
from miami_scoring.replay import replay_output_hash

# Hash is asserted equal to EXPECTED_HASH. When formulas legitimately change,
# bump `formula_version` in the YAML AND update this hash in the same PR.
EXPECTED_HASH = None  # populated after first successful CI run, then pinned


def _canonical_features() -> dict[str, object]:
    return {
        "momentum_14d": 0.12,
        "momentum_7d": 0.04,
        "momentum_30d": 0.18,
        "sources_present": ["pricecharting", "pokemontcg"],
        "listing_flow": {
            "active_listings": 14,
            "new_listings": 3,
            "estimated_disappeared_count": 2,
            "data_quality_score": 0.7,
        },
        "latest_market_price": 450.0,
        "grading_ev_inputs": {"p10": 0.34, "p9": 0.40, "population_growth_penalty": 0.0},
        "long_term_inputs": {"reprint_risk_score": 0.3},
        "ebay_input_weight": 0.3,
        "trailing_cross_source_agreement": True,
    }


def test_replay_hash_is_deterministic() -> None:
    formulas = load_active_formulas()
    features = _canonical_features()
    output1 = asdict(score(features, formulas))
    output2 = asdict(score(features, formulas))
    h1 = replay_output_hash([output1])
    h2 = replay_output_hash([output2])
    assert h1 == h2, "score() must be deterministic"

    if EXPECTED_HASH is not None:
        assert h1 == EXPECTED_HASH, (
            f"Scoring output changed from pinned hash. If intentional: bump formula_version "
            f"and update EXPECTED_HASH. Got {h1}"
        )


def test_replay_output_is_json_serializable() -> None:
    formulas = load_active_formulas()
    features = _canonical_features()
    out = score(features, formulas)
    json.dumps(asdict(out), default=str)  # must not raise
