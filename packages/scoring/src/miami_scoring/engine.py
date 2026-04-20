"""score() — pure function. Enforces the confidence cap in code, not policy.

Hard architectural invariant:
- Live scoring NEVER reads `retrospective_validation_score` or any column populated
  only by retrospective/backtest runs. The AST check
  `apps/api/tests/test_no_forward_reads.py` enforces this at CI time. The column
  names are intentionally listed here so the AST walker can grep for them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from miami_scoring.formula_loader import ActiveFormulas, FormulaDef

# Explicit disallow-list: the AST check imports and walks for reads of these names.
FORBIDDEN_FORWARD_READ_FIELDS: tuple[str, ...] = ("retrospective_validation_score",)


@dataclass(slots=True)
class ScoreOutput:
    breakout_score: float | None
    arbitrage_score: float | None
    long_term_score: float | None
    confidence_raw: float
    confidence_label: str
    ebay_input_weight: float
    trailing_cross_source_agreement: bool
    recommendation_label: str | None
    explanations: list[str]
    inputs_hash: str


def score(features: dict[str, object], formulas: ActiveFormulas) -> ScoreOutput:
    """Compute all four scores + confidence from an as-of feature payload.

    `features` is the `features_json` payload for one (entity, subject_variant, as_of_date).
    Contract:
    - No key in `features` whose name appears in FORBIDDEN_FORWARD_READ_FIELDS is touched.
    - `ebay_input_weight` passed on `features["ebay_input_weight"]` is the authoritative
      mix; formula YAML `ebay_dominant_inputs` is advisory only.
    """
    for field in FORBIDDEN_FORWARD_READ_FIELDS:
        if field in features:
            # Loud failure rather than silent lookahead. Live scoring should never get
            # passed these fields; a test fixture that does is a bug to fix.
            raise RuntimeError(f"forbidden forward-read field present: {field}")

    ebay_input_weight = float(features.get("ebay_input_weight", 0.0))  # type: ignore[arg-type]
    trailing_agreement = bool(features.get("trailing_cross_source_agreement", False))
    explanations: list[str] = []

    breakout = _breakout_score(features, formulas.breakout, explanations)
    arbitrage = _arbitrage_score(features, formulas.arbitrage, explanations)
    long_term = _long_term_score(features, formulas.long_term, explanations)

    confidence_raw = _confidence_raw(features, ebay_input_weight, trailing_agreement)
    confidence_label = _label_from_buckets(
        confidence_raw, formulas.breakout.definition["confidence_label_buckets"]
    )

    # Enforce cap from the breakout formula (all formulas share the same cap policy
    # in v1; check the most stringent one).
    cap_cfg = formulas.breakout.definition["confidence_cap"]
    if ebay_input_weight > float(cap_cfg["ebay_weight_threshold"]) and not trailing_agreement:
        clamp_to: Literal["High", "Medium", "Low", "Experimental"] = cap_cfg["clamp_to"]
        if _label_rank(confidence_label) > _label_rank(clamp_to):
            confidence_label = clamp_to
            explanations.append(f"confidence_clamped_to_{clamp_to.lower()}_due_to_ebay_dominance")

    recommendation = _recommendation_label(breakout, arbitrage, long_term, confidence_label)
    inputs_hash = hashlib.sha256(
        json.dumps(features, sort_keys=True, default=str).encode()
    ).hexdigest()

    return ScoreOutput(
        breakout_score=breakout,
        arbitrage_score=arbitrage,
        long_term_score=long_term,
        confidence_raw=confidence_raw,
        confidence_label=confidence_label,
        ebay_input_weight=ebay_input_weight,
        trailing_cross_source_agreement=trailing_agreement,
        recommendation_label=recommendation,
        explanations=explanations,
        inputs_hash=inputs_hash,
    )


# ---------- per-formula implementations ----------


def _breakout_score(
    features: dict[str, object], formula: FormulaDef, explanations: list[str]
) -> float | None:
    weights = formula.definition["weights"]
    momentum_14d = features.get("momentum_14d")
    flow = features.get("listing_flow") or {}  # type: ignore[assignment]
    # v1 uses proxy inputs; v2 will z-score these within cohort.
    price_mom_z = (
        _clip(float(momentum_14d), -1, 1) if isinstance(momentum_14d, (int, float)) else 0.0
    )
    active = (flow or {}).get("active_listings") if isinstance(flow, dict) else None
    dema = 0.0  # without history we have no demand-pressure estimate in v1a
    sat = 0.0
    depletion = 0.0
    replen = 0.0
    fvg_neg = 0.0
    social = 0.0

    score_val = (
        weights["price_momentum_14d"] * price_mom_z
        + weights["demand_pressure"] * dema
        + weights["supply_saturation_shift"] * sat
        + weights["price_band_depletion"] * depletion
        + weights["replenishment_inverse"] * replen
        + weights["fair_value_gap_negative"] * fvg_neg
        + weights["social_spike"] * social
    )
    if active is None:
        explanations.append("breakout_limited_history")
    return round(score_val, 4)


def _arbitrage_score(
    features: dict[str, object], formula: FormulaDef, explanations: list[str]
) -> float | None:
    ev_inputs = features.get("grading_ev_inputs") or {}
    latest = features.get("latest_market_price")
    if not isinstance(ev_inputs, dict) or latest is None:
        return None
    p10 = ev_inputs.get("p10")
    p9 = ev_inputs.get("p9")
    if p10 is None or p9 is None:
        return None
    fees = formula.definition["fee_constants"]
    # v1: assume the raw price lives alongside the graded price as "latest_market_price"
    # on the raw feature row; here we're in the graded row, so latest is the graded price.
    # We can't compute a full arbitrage score without joining raw + psa10 in this scope.
    # Return a normalized "grading-EV lite" signal instead.
    net_psa_factor = (
        1.0 - float(fees["marketplace_fee_rate"]) - float(fees["sales_tax_buffer_rate"])
    )
    expected = float(p10) * float(latest) * net_psa_factor
    return round(expected / float(latest) - 1.0, 4)


def _long_term_score(
    features: dict[str, object], formula: FormulaDef, explanations: list[str]
) -> float | None:
    weights = formula.definition["weights"]
    long_inputs = features.get("long_term_inputs") or {}
    reprint_risk = (
        (long_inputs or {}).get("reprint_risk_score") if isinstance(long_inputs, dict) else None
    )
    if reprint_risk is None:
        reprint_risk = 0.5
    # v1 produces a bounded signal dominated by reprint-risk inversion;
    # v2 will bring in fair-value gap, character premium, etc.
    return round(weights["low_reprint_risk"] * (1.0 - float(reprint_risk)), 4)


def _confidence_raw(
    features: dict[str, object], ebay_input_weight: float, trailing_agreement: bool
) -> float:
    """Scaled 0..1 based on source quality, history depth, and agreement.

    Only uses trailing inputs. v1: coarse heuristic; v2: replace with explicit
    calibration against backtest accuracy.
    """
    flow = features.get("listing_flow") if isinstance(features.get("listing_flow"), dict) else {}
    sources = features.get("sources_present") or []
    source_coverage = min(1.0, len(sources) / 2.0)  # 2+ sources = full credit
    data_quality = float((flow or {}).get("data_quality_score") or 0.6)
    agreement_bump = 0.15 if trailing_agreement else 0.0
    ebay_penalty = 0.2 * max(0.0, ebay_input_weight - 0.4)

    raw = 0.4 * source_coverage + 0.4 * data_quality + agreement_bump - ebay_penalty
    return round(max(0.0, min(1.0, raw)), 4)


def _label_from_buckets(raw: float, buckets: dict[str, float]) -> str:
    # buckets keys in descending order
    for label in ("High", "Medium", "Low", "Experimental"):
        if raw >= float(buckets[label]):
            return label
    return "Experimental"


_RANK = {"High": 4, "Medium": 3, "Low": 2, "Experimental": 1}


def _label_rank(label: str) -> int:
    return _RANK.get(label, 0)


def _recommendation_label(
    breakout: float | None,
    arbitrage: float | None,
    long_term: float | None,
    confidence_label: str,
) -> str | None:
    if confidence_label in {"Low", "Experimental"}:
        return "noisy"
    if breakout is not None and breakout > 0.6 and confidence_label in {"High", "Medium"}:
        return "early_breakout"
    if arbitrage is not None and arbitrage > 0.25:
        return "grading_candidate"
    if long_term is not None and long_term > 0.05:
        return "accumulation"
    return None


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
