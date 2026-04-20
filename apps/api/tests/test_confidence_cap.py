"""Confidence cap enforcement. Regardless of raw score magnitude, an eBay-dominated
feature vector without trailing cross-source agreement must be clamped to Medium.

The cap is a rank-only clamp: it only pulls labels DOWN to Medium (it never promotes
a Low score). Therefore this fixture must produce a pre-cap label above Medium
(i.e., High) so the clamp has something to do. Computing backward against
_confidence_raw:

    raw = 0.4 * source_coverage + 0.4 * data_quality + 0.15 * agreement_bump
        - 0.2 * max(0, ebay_input_weight - 0.4)

We want raw >= 0.75 (High) WITHOUT agreement_bump (setting trailing_cross_source_agreement
to True disables the clamp entirely). With source_coverage=1.0, data_quality=1.0,
ebay_input_weight=0.5 (still > 0.4 so the cap triggers): raw = 0.4 + 0.4 - 0.02 = 0.78 → High.
"""

from miami_scoring import load_active_formulas, score


def test_confidence_cap_clamps_ebay_dominated_without_agreement() -> None:
    formulas = load_active_formulas()
    features = {
        "momentum_14d": 0.3,
        "momentum_7d": 0.2,
        "momentum_30d": 0.4,
        # ≥ 2 sources so source_coverage = 1.0
        "sources_present": ["pricecharting", "pokemontcg"],
        "listing_flow": {
            "active_listings": 25,
            "new_listings": 15,
            "estimated_disappeared_count": 5,
            "data_quality_score": 1.0,  # maxes the data-quality term
        },
        "latest_market_price": 500.0,
        "ebay_input_weight": 0.5,  # above 0.4 threshold; small penalty keeps raw in High
        "trailing_cross_source_agreement": False,  # disables agreement_bump, triggers cap
    }
    out = score(features, formulas)
    # Raw confidence should be well above the Medium threshold (expect ~0.78 → "High")
    # but the cap must clamp the label down to Medium because of eBay dominance + no agreement.
    assert out.confidence_raw >= 0.55, (
        f"Pre-cap raw confidence {out.confidence_raw} too low to meaningfully test the cap"
    )
    assert out.confidence_label == "Medium", (
        f"Expected clamp to Medium; got {out.confidence_label} (raw={out.confidence_raw})"
    )
    assert any("confidence_clamped_to_medium" in note for note in out.explanations), (
        f"Expected clamp explanation in {out.explanations}"
    )


def test_confidence_not_clamped_when_agreement_is_true() -> None:
    formulas = load_active_formulas()
    features = {
        "momentum_14d": 0.2,
        "sources_present": ["pricecharting", "pokemontcg"],
        "listing_flow": {"data_quality_score": 0.8, "active_listings": 10},
        "latest_market_price": 500.0,
        "ebay_input_weight": 0.6,
        "trailing_cross_source_agreement": True,
    }
    out = score(features, formulas)
    # Agreement disables the cap; the formula's raw label stands.
    assert not any("confidence_clamped_to" in note for note in out.explanations), (
        f"Unexpected clamp in {out.explanations}"
    )


def test_confidence_not_promoted_when_already_below_cap() -> None:
    """The cap is a one-way pull. It must never promote a Low label to Medium."""
    formulas = load_active_formulas()
    features = {
        "momentum_14d": 0.1,
        "sources_present": ["ebay"],  # single source → 0.5 coverage
        "listing_flow": {"data_quality_score": 0.4, "active_listings": 5},
        "latest_market_price": 100.0,
        "ebay_input_weight": 0.9,
        "trailing_cross_source_agreement": False,
    }
    out = score(features, formulas)
    # Raw confidence is low; label should land at Low/Experimental, never Medium.
    assert out.confidence_label in {"Low", "Experimental"}, (
        f"Cap must not promote a low label; got {out.confidence_label}"
    )
