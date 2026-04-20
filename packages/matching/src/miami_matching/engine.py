"""Three-valued matcher. matched / ambiguous / rejected.

Rules are declared per candidate entity (card or sealed_product) cross subject_variant
(raw / psa10 / psa9 / psa_other / sealed). Each rule has include_terms, exclude_terms,
and regex_patterns. Match confidence is the Jaccard-like overlap between title tokens
and include_terms, adjusted by exclude hits and variant/grade consistency.

Confidence thresholds:
- >= 0.75 and exactly one winning candidate → `matched`
- >= 0.60 and multiple candidates tied within 0.05 → `ambiguous`
- otherwise → `rejected`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from miami_matching.tokenize import TitleTokens, tokenize_title


class MatchDecision(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RuleDef:
    """One matcher rule. Keyed by (entity_type, entity_id, subject_variant)."""

    entity_type: str
    entity_id: int
    subject_variant: str
    include_terms: tuple[str, ...]
    exclude_terms: tuple[str, ...] = ()
    regex_patterns: tuple[str, ...] = ()
    min_confidence: float = 0.6
    # If the listing title contains a detected card_number AND this is set, the
    # numbers must match. Prevents near-miss card collisions ("125/197" vs "199/197").
    expected_card_number: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateScore:
    rule: RuleDef
    score: float
    hits: tuple[str, ...]
    misses: tuple[str, ...]


@dataclass(slots=True)
class MatchResult:
    decision: MatchDecision
    rule_version: str
    best_rule: RuleDef | None
    confidence: float
    all_candidates: list[CandidateScore] = field(default_factory=list)
    tokens: TitleTokens | None = None

    def as_observation(self) -> dict[str, object]:
        """Shape that maps to match_observation row columns."""
        if self.best_rule is not None and self.decision == MatchDecision.MATCHED:
            matched_entity_type: str | None = self.best_rule.entity_type
            matched_entity_id: int | None = self.best_rule.entity_id
            matched_subject_variant: str | None = self.best_rule.subject_variant
        else:
            matched_entity_type = None
            matched_entity_id = None
            matched_subject_variant = None
        tokens = self.tokens
        return {
            "decision": self.decision.value,
            "match_confidence": self.confidence,
            "rule_version": self.rule_version,
            "matched_entity_type": matched_entity_type,
            "matched_entity_id": matched_entity_id,
            "matched_subject_variant": matched_subject_variant,
            "detected_set_code": None,
            "detected_card_number": tokens.detected_card_number if tokens else None,
            "detected_variant": (
                ",".join(sorted(tokens.detected_variant))
                if tokens and tokens.detected_variant
                else None
            ),
            "detected_grade": (
                f"{tokens.detected_grade_company} {tokens.detected_grade}"
                if tokens and tokens.detected_grade_company and tokens.detected_grade
                else None
            ),
        }


class RuleRepo(Protocol):
    def all_rules(self) -> list[RuleDef]: ...


@dataclass(frozen=True, slots=True)
class MatcherConfig:
    match_threshold: float = 0.75
    ambiguity_margin: float = 0.05
    ambiguous_floor: float = 0.60


class Matcher:
    """Runs the rule set against a single title and returns a MatchResult.

    Designed for pure computation; does no I/O. Inject rules via RuleRepo.
    """

    def __init__(
        self, rules: list[RuleDef], rule_version: str, config: MatcherConfig | None = None
    ):
        self._rules = rules
        self._rule_version = rule_version
        self._config = config or MatcherConfig()
        # Precompile regexes once.
        self._regex_cache: dict[str, re.Pattern[str]] = {}

    def _compile(self, pattern: str) -> re.Pattern[str]:
        if pattern not in self._regex_cache:
            self._regex_cache[pattern] = re.compile(pattern, re.IGNORECASE)
        return self._regex_cache[pattern]

    def _score_rule(self, rule: RuleDef, tokens: TitleTokens) -> CandidateScore:
        # Fast reject: any exclude term present → score 0.
        misses_excludes = [term for term in rule.exclude_terms if term in tokens.normalized]
        if misses_excludes:
            return CandidateScore(rule=rule, score=0.0, hits=(), misses=tuple(misses_excludes))

        # Subject-variant consistency with detected grade.
        if rule.subject_variant == "raw" and tokens.detected_grade_company is not None:
            return CandidateScore(
                rule=rule, score=0.0, hits=(), misses=("detected_grade_on_raw_rule",)
            )
        if rule.subject_variant in {"psa10", "psa9", "psa_other"}:
            if tokens.detected_grade_company != "PSA":
                return CandidateScore(
                    rule=rule, score=0.0, hits=(), misses=("wrong_grade_company",)
                )
            grade = tokens.detected_grade or ""
            if rule.subject_variant == "psa10" and grade != "10":
                return CandidateScore(rule=rule, score=0.0, hits=(), misses=("wrong_psa_grade",))
            if rule.subject_variant == "psa9" and grade != "9":
                return CandidateScore(rule=rule, score=0.0, hits=(), misses=("wrong_psa_grade",))

        # Language consistency — if rule is English and title is flagged Japanese, reject.
        if rule.subject_variant != "sealed" and tokens.likely_japanese:
            return CandidateScore(rule=rule, score=0.0, hits=(), misses=("japanese_rejected",))

        # Card-number consistency. If the title has an explicit card number and the
        # rule declares (or implies) an expected one, mismatches are hard rejects.
        expected = rule.expected_card_number
        if expected is None and rule.entity_type == "card":
            # Infer from include_terms (any token matching NNN/MMM is the expected number).
            for term in rule.include_terms:
                if "/" in term and term.replace("/", "").isdigit():
                    expected = term
                    break
        if expected is not None and tokens.detected_card_number is not None:
            expected_number = expected.split("/")[0].lstrip("0") or "0"
            if tokens.detected_card_number != expected_number:
                return CandidateScore(
                    rule=rule, score=0.0, hits=(), misses=("card_number_mismatch",)
                )

        hits: list[str] = []
        misses: list[str] = []
        for term in rule.include_terms:
            if term.lower() in tokens.normalized:
                hits.append(term)
            else:
                misses.append(term)

        regex_bonus = 0.0
        for pattern in rule.regex_patterns:
            if self._compile(pattern).search(tokens.normalized):
                regex_bonus += 0.1

        if not rule.include_terms:
            return CandidateScore(rule=rule, score=0.0, hits=(), misses=())

        # Core score: fraction of include_terms hit, with regex bonus, clamped at 1.
        base = len(hits) / len(rule.include_terms)
        score = min(1.0, base + regex_bonus)
        return CandidateScore(rule=rule, score=score, hits=tuple(hits), misses=tuple(misses))

    def match(self, raw_title: str) -> MatchResult:
        tokens = tokenize_title(raw_title)
        candidates = [self._score_rule(r, tokens) for r in self._rules]
        # Drop 0-score candidates.
        candidates = sorted(
            (c for c in candidates if c.score > 0), key=lambda c: c.score, reverse=True
        )

        if not candidates:
            return MatchResult(
                decision=MatchDecision.REJECTED,
                rule_version=self._rule_version,
                best_rule=None,
                confidence=0.0,
                all_candidates=[],
                tokens=tokens,
            )

        top = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        # Tie detection within a narrow margin → ambiguous.
        if (
            runner_up is not None
            and top.score >= self._config.ambiguous_floor
            and (top.score - runner_up.score) < self._config.ambiguity_margin
        ):
            return MatchResult(
                decision=MatchDecision.AMBIGUOUS,
                rule_version=self._rule_version,
                best_rule=top.rule,
                confidence=top.score,
                all_candidates=candidates,
                tokens=tokens,
            )

        if top.score >= max(self._config.match_threshold, top.rule.min_confidence):
            return MatchResult(
                decision=MatchDecision.MATCHED,
                rule_version=self._rule_version,
                best_rule=top.rule,
                confidence=top.score,
                all_candidates=candidates,
                tokens=tokens,
            )

        return MatchResult(
            decision=MatchDecision.REJECTED,
            rule_version=self._rule_version,
            best_rule=top.rule,
            confidence=top.score,
            all_candidates=candidates,
            tokens=tokens,
        )
