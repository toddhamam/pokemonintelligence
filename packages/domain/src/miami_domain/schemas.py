"""Pydantic response schemas for the FastAPI contract.

These are the single source of truth for the JSON shapes the frontend consumes.
`openapi-typescript` regenerates `apps/web/src/generated/api.ts` from the FastAPI
OpenAPI spec; CI fails on drift.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["card", "sealed_product"]
SubjectVariant = Literal["raw", "psa10", "psa9", "psa_other", "sealed"]
ConfidenceLabel = Literal["High", "Medium", "Low", "Experimental"]


class _BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---------- catalog ----------
class SetOut(_BaseSchema):
    id: int
    name: str
    series: str | None = None
    language: str
    release_date: date | None = None
    set_type: str | None = None


class CardOut(_BaseSchema):
    id: int
    set_id: int
    name: str
    card_number: str
    rarity: str | None = None
    pokemon_name: str | None = None
    language: str
    is_promo: bool
    is_playable: bool


class SealedProductOut(_BaseSchema):
    id: int
    set_id: int
    product_name: str
    product_type: str
    msrp: Decimal | None = None
    exclusive_type: str | None = None


# ---------- history (time series) ----------
class PricePoint(_BaseSchema):
    observed_date: date
    source: str
    market_price: Decimal | None = None
    low_price: Decimal | None = None
    high_price: Decimal | None = None
    confidence: float


class PopulationPoint(_BaseSchema):
    observed_date: date
    grade_company: str
    total_population: int
    grade_10_population: int
    grade_9_population: int


# ---------- scores & rankings ----------
class ScoresBlock(_BaseSchema):
    breakout: float | None = None
    arbitrage: float | None = None
    long_term: float | None = None
    confidence_raw: float
    confidence_label: ConfidenceLabel
    label: str | None = None


class RankingRow(_BaseSchema):
    entity_type: EntityType
    entity_id: int
    subject_variant: SubjectVariant
    name: str
    set_name: str | None = None
    scores: ScoresBlock
    snapshot_date: date
    explanations: list[str] = Field(default_factory=list)


class FairValueOut(_BaseSchema):
    estimate: Decimal | None = None
    lower_band: Decimal | None = None
    upper_band: Decimal | None = None
    drivers: dict[str, float] = Field(default_factory=dict)
    confidence_label: ConfidenceLabel


class GradingEvOut(_BaseSchema):
    ev_per_card: Decimal | None = None
    ev_per_dollar: float | None = None
    p10: float | None = None
    p9: float | None = None
    drivers: dict[str, float] = Field(default_factory=dict)
    confidence_label: ConfidenceLabel


class ConfidenceBreakdown(_BaseSchema):
    score: float
    label: ConfidenceLabel
    components: dict[str, float] = Field(default_factory=dict)


# ---------- alerts & watchlists ----------
class AlertRule(_BaseSchema):
    entity_type: EntityType | None = None
    subject_variant: SubjectVariant | None = None
    score: Literal["breakout_score", "arbitrage_score", "long_term_score"]
    op: Literal[">", ">=", "<", "<="]
    value: float
    min_confidence: float = 0.55
    channel: Literal["email"] = "email"


class AlertIn(_BaseSchema):
    name: str
    rule: AlertRule


class AlertOut(_BaseSchema):
    id: int
    name: str
    rule: AlertRule
    active: bool
    last_fired_at: str | None = None


# ---------- pagination ----------
class Page[T](_BaseSchema):
    items: list[T]
    next_cursor: str | None = None
