"""Scoring engine. Pure functions over (features, formula_def) → score rows.

Confidence cap lives in `engine.score()` — not just in YAML. Retrospective validation
is a SEPARATE function that backtests invoke; live `score()` never reads forward data.
"""

from miami_scoring.engine import ScoreOutput, score
from miami_scoring.formula_loader import (
    ActiveFormulas,
    FormulaDef,
    load_active_formulas,
)
from miami_scoring.replay import replay
from miami_scoring.retrospective import retrospective_validate

__all__ = [
    "ActiveFormulas",
    "FormulaDef",
    "ScoreOutput",
    "load_active_formulas",
    "replay",
    "retrospective_validate",
    "score",
]
