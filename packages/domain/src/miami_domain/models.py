"""SQLAlchemy ORM mappings — mirror the Alembic 0001 schema.

Kept lean: snapshot/fact tables use `Mapped` columns only where we actually join in Python;
everything else is accessed via raw SQL or Polars read_database for throughput.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict] = {
        dict[str, Any]: JSONB,
        list[str]: ARRAY(String),
    }


class Set(Base):
    __tablename__ = "set"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tcgplayer_group_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    name: Mapped[str]
    series: Mapped[str | None]
    language: Mapped[str] = mapped_column(default="en")
    release_date: Mapped[date | None] = mapped_column(Date)
    set_type: Mapped[str | None]
    has_booster_box: Mapped[bool] = mapped_column(Boolean, default=True)
    has_special_product_only: Mapped[bool] = mapped_column(Boolean, default=False)
    msrp_pack: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    msrp_etb: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    msrp_booster_box: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pack_count_per_box: Mapped[int | None]
    cards_per_pack: Mapped[int | None]
    slot_distribution_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    official_pack_odds_source: Mapped[str | None]
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cards: Mapped[list["Card"]] = relationship(back_populates="set", lazy="noload")
    sealed_products: Mapped[list["SealedProduct"]] = relationship(
        back_populates="set", lazy="noload"
    )

    __table_args__ = (Index("ix_set_language_release", "language", "release_date"),)


class Card(Base):
    __tablename__ = "card"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    set_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("set.id"))
    tcgplayer_product_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    pricecharting_id: Mapped[str | None] = mapped_column(unique=True)
    pokemontcg_id: Mapped[str | None] = mapped_column(unique=True)
    psa_key: Mapped[str | None] = mapped_column(unique=True)
    name: Mapped[str]
    card_number: Mapped[str]
    rarity: Mapped[str | None]
    sub_rarity: Mapped[str | None]
    pokemon_name: Mapped[str | None]
    language: Mapped[str] = mapped_column(default="en")
    art_variant: Mapped[str | None]
    illustrator: Mapped[str | None]
    is_promo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_playable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_full_art: Mapped[bool] = mapped_column(Boolean, default=False)
    is_alt_art: Mapped[bool] = mapped_column(Boolean, default=False)
    rarity_slot_id: Mapped[int | None] = mapped_column(BigInteger)
    condition_scope_default: Mapped[str | None]
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    set: Mapped[Set] = relationship(back_populates="cards", lazy="noload")

    __table_args__ = (
        UniqueConstraint("set_id", "card_number"),
        Index("ix_card_pokemon_name", "pokemon_name"),
    )


class SealedProduct(Base):
    __tablename__ = "sealed_product"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    set_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("set.id"))
    tcgplayer_product_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    product_name: Mapped[str]
    product_type: Mapped[str]
    msrp: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    sku_aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    official_url: Mapped[str | None]
    exclusive_type: Mapped[str | None]
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    set: Mapped[Set] = relationship(back_populates="sealed_products", lazy="noload")

    __table_args__ = (Index("ix_sealed_product_set", "set_id"),)


class RaritySlot(Base):
    __tablename__ = "rarity_slot"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    set_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("set.id"))
    slot_name: Mapped[str]
    slot_probability: Mapped[float]
    cards_in_slot: Mapped[int]

    __table_args__ = (UniqueConstraint("set_id", "slot_name"),)


class MatchRule(Base):
    __tablename__ = "match_rule"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_version: Mapped[str]
    entity_type: Mapped[str]
    entity_id: Mapped[int] = mapped_column(BigInteger)
    subject_variant: Mapped[str]
    include_terms: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    exclude_terms: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    regex_patterns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    min_confidence: Mapped[float] = mapped_column(default=0.6)
    applied_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    applied_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("entity_type IN ('card', 'sealed_product')"),
        CheckConstraint("subject_variant IN ('raw', 'psa10', 'psa9', 'psa_other', 'sealed')"),
        UniqueConstraint("rule_version", "entity_type", "entity_id", "subject_variant"),
    )


class AliasRule(Base):
    __tablename__ = "alias_rule"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_version: Mapped[str]
    entity_type: Mapped[str]
    entity_id: Mapped[int] = mapped_column(BigInteger)
    alias: Mapped[str]

    __table_args__ = (UniqueConstraint("rule_version", "entity_type", "entity_id", "alias"),)


# ---------- snapshot facts (lean orm; used for writes; reads go through Polars) ----------
class PriceSnapshotDaily(Base):
    __tablename__ = "price_snapshot_daily"
    observed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    card_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(primary_key=True)
    source_record_id: Mapped[str]
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    mid_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    near_mint_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    modeled_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(CHAR(3), default="USD")
    confidence: Mapped[float]
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    job_run_id: Mapped[int | None] = mapped_column(BigInteger)


class GradedSnapshotDaily(Base):
    __tablename__ = "graded_snapshot_daily"
    observed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    card_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(primary_key=True)
    grade_company: Mapped[str] = mapped_column(primary_key=True)
    grade: Mapped[str] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(primary_key=True)
    source_record_id: Mapped[str]
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    modeled_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(CHAR(3), default="USD")
    confidence: Mapped[float]
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    job_run_id: Mapped[int | None] = mapped_column(BigInteger)


class SealedSnapshotDaily(Base):
    __tablename__ = "sealed_snapshot_daily"
    observed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    sealed_product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(primary_key=True)
    source_record_id: Mapped[str]
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    modeled_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(CHAR(3), default="USD")
    confidence: Mapped[float]
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    job_run_id: Mapped[int | None] = mapped_column(BigInteger)


class ListingFlowSnapshot(Base):
    __tablename__ = "listing_flow_snapshot"
    observed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    entity_type: Mapped[str] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_variant: Mapped[str] = mapped_column(primary_key=True)
    active_listings: Mapped[int] = mapped_column(default=0)
    new_listings: Mapped[int] = mapped_column(default=0)
    estimated_disappeared_count: Mapped[int] = mapped_column(default=0)
    avg_listing_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    median_listing_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_band_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    avg_days_active: Mapped[float | None]
    overmatch_count: Mapped[int] = mapped_column(default=0)
    discarded_count: Mapped[int] = mapped_column(default=0)
    match_rules_version: Mapped[str]
    data_quality_score: Mapped[float]
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    job_run_id: Mapped[int | None] = mapped_column(BigInteger)


class PopulationSnapshot(Base):
    __tablename__ = "population_snapshot"
    observed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    card_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    grade_company: Mapped[str] = mapped_column(primary_key=True)
    total_population: Mapped[int]
    grade_10_population: Mapped[int]
    grade_9_population: Mapped[int]
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    job_run_id: Mapped[int | None] = mapped_column(BigInteger)


class RetailStockSnapshot(Base):
    __tablename__ = "retail_stock_snapshot"
    observed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sealed_product_id: Mapped[int] = mapped_column(BigInteger)
    retailer: Mapped[str]
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    in_stock: Mapped[bool]
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    restock_signal: Mapped[str | None]
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    job_run_id: Mapped[int | None] = mapped_column(BigInteger)


class ListingIdentity(Base):
    __tablename__ = "listing_identity"
    source: Mapped[str] = mapped_column(primary_key=True)
    source_listing_id: Mapped[str] = mapped_column(primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    first_decision: Mapped[str]
    last_decision: Mapped[str]
    latest_rule_version: Mapped[str]
    latest_matched_entity_type: Mapped[str | None]
    latest_matched_entity_id: Mapped[int | None] = mapped_column(BigInteger)
    latest_matched_subject_variant: Mapped[str | None]


class MatchObservation(Base):
    __tablename__ = "match_observation"
    observed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    source: Mapped[str] = mapped_column(primary_key=True)
    source_listing_id: Mapped[str] = mapped_column(primary_key=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decision: Mapped[str]
    match_confidence: Mapped[float]
    rule_version: Mapped[str]
    matched_entity_type: Mapped[str | None]
    matched_entity_id: Mapped[int | None] = mapped_column(BigInteger)
    matched_subject_variant: Mapped[str | None]
    detected_set_code: Mapped[str | None]
    detected_card_number: Mapped[str | None]
    detected_variant: Mapped[str | None]
    detected_grade: Mapped[str | None]
    features_blob_key: Mapped[str]
    job_run_id: Mapped[int | None] = mapped_column(BigInteger)


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshot"
    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True)
    entity_type: Mapped[str] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_variant: Mapped[str] = mapped_column(primary_key=True)
    feature_set_version: Mapped[str] = mapped_column(primary_key=True)
    features_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ebay_input_weight: Mapped[float] = mapped_column(default=0.0)
    trailing_cross_source_agreement: Mapped[bool] = mapped_column(Boolean, default=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshot"
    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True)
    entity_type: Mapped[str] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_variant: Mapped[str] = mapped_column(primary_key=True)
    formula_version: Mapped[str] = mapped_column(primary_key=True)
    feature_set_version: Mapped[str]
    inputs_hash: Mapped[str]
    breakout_score: Mapped[float | None]
    arbitrage_score: Mapped[float | None]
    long_term_score: Mapped[float | None]
    confidence_raw: Mapped[float]
    confidence_label: Mapped[str]
    ebay_input_weight: Mapped[float] = mapped_column(default=0.0)
    trailing_cross_source_agreement: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation_label: Mapped[str | None]
    explanations: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Populated ONLY by backtest runs. Live score() MUST NOT read this.
    retrospective_validation_score: Mapped[float | None]
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ScoringFormula(Base):
    __tablename__ = "scoring_formula"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str]
    version: Mapped[str]
    git_sha: Mapped[str]
    content_hash: Mapped[str]
    definition_yaml: Mapped[str]
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("name", "version"),)


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_name: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="running")
    rows_in: Mapped[int | None]
    rows_out: Mapped[int | None]
    error_text: Mapped[str | None]
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Alert(Base):
    __tablename__ = "alert"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str]
    name: Mapped[str]
    rule_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    channel: Mapped[str] = mapped_column(default="email")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertEvent(Base):
    __tablename__ = "alert_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alert_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("alert.id"))
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    entity_type: Mapped[str]
    entity_id: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    formula_version: Mapped[str]
    feature_set_version: Mapped[str]
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None]
