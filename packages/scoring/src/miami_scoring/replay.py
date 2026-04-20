"""replay() — deterministic backtest entrypoint.

Loads persisted features at (as_of_date, feature_set_version), applies score() with the
requested formula_version, returns a list[dict]. CI asserts SHA256 of the output is
stable across commits for a pinned fixture.

This function does NOT rebuild features from raw snapshots; that's build_features().
Together they are the two reproducibility entrypoints described in the plan.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date

from sqlalchemy import text

from miami_common.db import session_feature_compute
from miami_scoring.engine import ScoreOutput, score
from miami_scoring.formula_loader import load_active_formulas


def replay(
    as_of_date: date,
    formula_version: str,
    feature_set_version: str,
) -> list[dict[str, object]]:
    formulas = load_active_formulas()
    # For v1 we only support replay at HEAD formulas; v2 will load prior versions from
    # `scoring_formula` rows by `(name, version)`.
    if formulas.breakout.version != formula_version:
        raise ValueError(
            f"Only HEAD formula version {formulas.breakout.version} is loadable in v1; "
            f"requested {formula_version}"
        )

    rows: list[dict[str, object]] = []
    with session_feature_compute() as s:
        feature_rows = (
            s.execute(
                text(
                    """
                SELECT entity_type, entity_id, subject_variant, features_json,
                       ebay_input_weight, trailing_cross_source_agreement
                FROM feature_snapshot
                WHERE as_of_date = :d AND feature_set_version = :v
                ORDER BY entity_type, entity_id, subject_variant
                """
                ),
                {"d": as_of_date, "v": feature_set_version},
            )
            .mappings()
            .all()
        )

    for fr in feature_rows:
        features = dict(fr["features_json"])
        features["ebay_input_weight"] = float(fr["ebay_input_weight"])
        features["trailing_cross_source_agreement"] = bool(fr["trailing_cross_source_agreement"])
        output: ScoreOutput = score(features, formulas)
        rows.append(
            {
                "entity_type": fr["entity_type"],
                "entity_id": int(fr["entity_id"]),
                "subject_variant": fr["subject_variant"],
                "as_of_date": as_of_date.isoformat(),
                "formula_version": formula_version,
                "feature_set_version": feature_set_version,
                **asdict(output),
            }
        )
    return rows


def replay_output_hash(rows: list[dict[str, object]]) -> str:
    """Deterministic hash of replay output for CI pinning."""
    payload = json.dumps(rows, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()
