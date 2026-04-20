"""CI gate for the matcher. Phase 1 blocks Phase 3 until this passes.

Thresholds from the plan: precision ≥ 0.90, recall ≥ 0.70. The labeled fixture
(`apps/api/tests/fixtures/ebay_titles_labeled.jsonl`) is the source of truth; every
rule_version bump re-measures against the same fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from miami_matching import RULE_VERSION, Matcher, MatcherConfig
from miami_matching.engine import MatchDecision
from miami_matching.seed_rules import default_seed_rules

FIXTURE = Path(__file__).parent / "fixtures" / "ebay_titles_labeled.jsonl"

PRECISION_MIN = 0.90
RECALL_MIN = 0.70


@pytest.fixture(scope="module")
def matcher() -> Matcher:
    return Matcher(
        rules=default_seed_rules(),
        rule_version=RULE_VERSION,
        config=MatcherConfig(),
    )


def _load_fixture() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in FIXTURE.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_precision_recall(matcher: Matcher) -> None:
    rows = _load_fixture()
    assert len(rows) >= 40, "Fixture too small to be meaningful"

    tp = 0  # matched AND correct entity
    fp = 0  # matched AND wrong/should-have-been-rejected
    fn = 0  # gold-labeled entity but matcher said rejected/ambiguous
    true_negatives = 0  # gold = null AND matcher rejected/ambiguous

    for row in rows:
        gold_entity_type = row["entity_type"]
        gold_entity_id = row["entity_id"]
        gold_subject = row["subject_variant"]
        result = matcher.match(row["title"])  # type: ignore[arg-type]

        if result.decision == MatchDecision.MATCHED:
            if (
                gold_entity_type is not None
                and result.best_rule is not None
                and result.best_rule.entity_type == gold_entity_type
                and result.best_rule.entity_id == gold_entity_id
                and result.best_rule.subject_variant == gold_subject
            ):
                tp += 1
            else:
                fp += 1
        else:
            if gold_entity_type is None:
                true_negatives += 1
            else:
                fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    print(
        f"matcher stats: tp={tp} fp={fp} fn={fn} tn={true_negatives} "
        f"precision={precision:.3f} recall={recall:.3f}"
    )

    assert precision >= PRECISION_MIN, f"Precision {precision:.3f} < {PRECISION_MIN}"
    assert recall >= RECALL_MIN, f"Recall {recall:.3f} < {RECALL_MIN}"
