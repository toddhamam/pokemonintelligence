# Formulas

Git-canonical YAML in `packages/scoring/src/miami_scoring/formulas/`. DB rows in
`scoring_formula` mirror with `git_sha` + `content_hash`; CI asserts no drift via
`verify_formula_hashes.py`.

## breakout v1.0.0

Inputs (all pre-z-scored in v2; v1 uses proxy normalization):

```
breakout_score =
    0.20 * price_momentum_14d
  + 0.20 * demand_pressure
  + 0.20 * (-supply_saturation_shift)
  + 0.15 * price_band_depletion
  + 0.10 * (-listing_replenishment_ratio)
  + 0.10 * (-fair_value_gap)
  + 0.05 * social_spike  # reserved for V2
```

**Live confidence cap (enforced in `score()` Python, not just YAML):** if
`ebay_input_weight > 0.4` AND `trailing_cross_source_agreement = false`, clamp
`confidence_label` to Medium regardless of raw score.

**Trailing cross-source agreement** is computed from `feature_snapshot` at `as_of_date`
using only data with `observed_date <= as_of_date`. Forward validation lives on
`score_snapshot.retrospective_validation_score` and is consumed ONLY by backtest runs.

## arbitrage v1.0.0

Grading EV (simplified, v1):

```
expected_grade_value = p10 * net_psa10 + p9 * net_psa9
grading_total_cost   = raw + grading_fee + shipping + insurance + marketplace_fees + tax_buffer + capital_time_cost
grading_ev           = expected_grade_value - grading_total_cost
arbitrage_score      = grading_ev / raw
```

Fee constants are in the YAML. v1 produces a partial signal because the graded
`score_snapshot` row doesn't see the raw price in the same scope; v2 will join raw +
psa10 via a shared feature vector.

## long_term v1.0.0

```
long_term_score =
    0.20 * fair_value_gap
  + 0.15 * character_premium
  + 0.15 * scarcity
  + 0.15 * product_structure
  + 0.10 * low_reprint_risk
  + 0.10 * stable_population_growth
  + 0.10 * retail_stock_constraint
  + 0.05 * anniversary_macro
```

v1 ships a reduced version dominated by `low_reprint_risk`; the remaining inputs
come online as the fair-value regression and catalog enrichment land in V2.

## confidence

`confidence_raw` = 0.4·source_coverage + 0.4·data_quality + 0.15·trailing_agreement − 0.2·max(0, ebay_input_weight − 0.4)

Buckets: High ≥ 0.75, Medium ≥ 0.55, Low ≥ 0.35, Experimental otherwise.

## Change procedure

Any change to a formula must:

1. Bump `version:` in the YAML (semver).
2. Update `apps/api/tests/test_replay_hash_stable.py::EXPECTED_HASH` (run replay, pin).
3. Add a row in `scoring_formula` via migration; `verify_formula_hashes.py` auto-mirrors
   new versions; CI asserts old versions still match their stored hash.
