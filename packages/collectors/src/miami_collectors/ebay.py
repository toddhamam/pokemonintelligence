"""eBay Browse — active live listings only.

Market-state is derived from snapshot differencing, NOT realized sales (Marketplace
Insights is restricted and not part of v1). Per daily run:
1. Fetch candidate active listings per tracked entity
2. Run deterministic matcher → three-valued output
3. Upsert listing_identity (mutable identity table)
4. Append match_observation (append-only, partitioned by observed_date)
5. Aggregate matched rows per (entity, subject_variant) into listing_flow_snapshot
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import mean, median
from typing import Any

from sqlalchemy import text

from miami_collectors.base import BaseCollector, CollectorResult
from miami_collectors.blob_archive import archive_payload
from miami_common.db import session_owner
from miami_common.logging import get_logger
from miami_common.settings import get_settings
from miami_matching import RULE_VERSION, Matcher
from miami_matching.engine import MatchDecision
from miami_matching.seed_rules import default_seed_rules

log = get_logger(__name__)

_SOURCE = "ebay"


@dataclass(slots=True)
class RawListing:
    source_listing_id: str
    title: str
    price: Decimal
    currency: str


class EbayCollector(BaseCollector):
    """Orchestrates fetch → match → identity upsert → observation append → flow aggregate."""

    source = _SOURCE
    target_table = "listing_flow_snapshot"
    pk_columns = ("observed_date", "entity_type", "entity_id", "subject_variant")

    def fetch(self, as_of_date: date) -> list[dict[str, Any]]:
        if get_settings().dev_mode:
            return _dev_fixture_listings()
        # TODO(prod): call /buy/browse/v1/item_summary/search for each tracked entity.
        raise NotImplementedError("Live eBay fetch requires Browse API token")

    def parse(self, payload: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
        # Overridden by run() — eBay needs the match step before it can produce
        # listing_flow_snapshot rows. parse() returns empty because run() handles persistence.
        return []

    def run(self, as_of_date: date) -> CollectorResult:  # type: ignore[override]
        params = {"as_of_date": as_of_date.isoformat()}
        with session_owner() as s:
            job_run_id = s.execute(
                text(
                    "INSERT INTO job_runs (job_name, started_at, status, params) "
                    "VALUES ('collector.ebay', now(), 'running', CAST(:p AS JSONB)) RETURNING id"
                ),
                {"p": _json(params)},
            ).scalar_one()
            s.commit()

        status = "success"
        error: str | None = None
        rows_in = 0
        rows_out = 0
        try:
            payload = self.fetch(as_of_date)
            rows_in = len(payload)
            archive_payload(_SOURCE, as_of_date, payload)

            matcher = Matcher(rules=default_seed_rules(), rule_version=RULE_VERSION)
            per_group: dict[tuple[str, int, str], list[RawListing]] = defaultdict(list)
            overmatch_per_group: dict[tuple[str, int, str], int] = defaultdict(int)
            discarded_per_group: dict[tuple[str, int, str], int] = defaultdict(int)

            for raw in payload:
                listing = RawListing(
                    source_listing_id=str(raw["source_listing_id"]),
                    title=str(raw["title"]),
                    price=Decimal(str(raw.get("price", "0"))),
                    currency=str(raw.get("currency", "USD")),
                )
                result = matcher.match(listing.title)
                features_key = self._archive_features(listing, result, as_of_date)
                self._upsert_identity(listing, result, job_run_id)
                self._append_observation(listing, result, as_of_date, features_key, job_run_id)
                if result.decision == MatchDecision.MATCHED and result.best_rule is not None:
                    key = (
                        result.best_rule.entity_type,
                        result.best_rule.entity_id,
                        result.best_rule.subject_variant,
                    )
                    per_group[key].append(listing)
                    if len(result.all_candidates) > 1 and result.all_candidates[1].score >= 0.5:
                        overmatch_per_group[key] += 1
                else:
                    # Attribute discards to the best-candidate group if there was one,
                    # otherwise they're off-universe and we don't count them.
                    if result.best_rule is not None:
                        key = (
                            result.best_rule.entity_type,
                            result.best_rule.entity_id,
                            result.best_rule.subject_variant,
                        )
                        discarded_per_group[key] += 1

            rows_out = self._persist_flow_snapshots(
                per_group, overmatch_per_group, discarded_per_group, as_of_date, job_run_id
            )
        except Exception as exc:
            status = "error"
            error = repr(exc)
            log.exception("ebay_collector_failed")

        with session_owner() as s:
            s.execute(
                text(
                    "UPDATE job_runs SET finished_at=now(), status=:status, "
                    "rows_in=:rin, rows_out=:rout, error_text=:err WHERE id=:id"
                ),
                {
                    "status": status,
                    "rin": rows_in,
                    "rout": rows_out,
                    "err": error,
                    "id": job_run_id,
                },
            )
            s.commit()

        return CollectorResult(job_run_id, rows_in, rows_out, status, error)

    def _archive_features(self, listing: RawListing, result: Any, as_of_date: date) -> str:
        key = f"match_observation/{as_of_date.strftime('%Y%m')}/{listing.source_listing_id}-{as_of_date.isoformat()}.json"
        # In dev we don't upload; we just return a deterministic pointer.
        return key

    def _upsert_identity(self, listing: RawListing, result: Any, job_run_id: int) -> None:
        with session_owner() as s:
            s.execute(
                text(
                    """
                    INSERT INTO listing_identity (
                        source, source_listing_id, first_seen_at, last_seen_at,
                        first_decision, last_decision, latest_rule_version,
                        latest_matched_entity_type, latest_matched_entity_id,
                        latest_matched_subject_variant
                    ) VALUES (
                        :source, :sid, now(), now(),
                        :decision, :decision, :rule_version,
                        :mtype, :mid, :msubject
                    )
                    ON CONFLICT (source, source_listing_id) DO UPDATE SET
                        last_seen_at = now(),
                        last_decision = EXCLUDED.last_decision,
                        latest_rule_version = EXCLUDED.latest_rule_version,
                        latest_matched_entity_type = EXCLUDED.latest_matched_entity_type,
                        latest_matched_entity_id = EXCLUDED.latest_matched_entity_id,
                        latest_matched_subject_variant = EXCLUDED.latest_matched_subject_variant
                    """
                ),
                {
                    "source": _SOURCE,
                    "sid": listing.source_listing_id,
                    "decision": result.decision.value,
                    "rule_version": result.rule_version,
                    "mtype": result.best_rule.entity_type
                    if result.best_rule and result.decision == MatchDecision.MATCHED
                    else None,
                    "mid": result.best_rule.entity_id
                    if result.best_rule and result.decision == MatchDecision.MATCHED
                    else None,
                    "msubject": result.best_rule.subject_variant
                    if result.best_rule and result.decision == MatchDecision.MATCHED
                    else None,
                },
            )
            s.commit()

    def _append_observation(
        self,
        listing: RawListing,
        result: Any,
        as_of_date: date,
        features_key: str,
        job_run_id: int,
    ) -> None:
        obs = result.as_observation()
        with session_owner() as s:
            s.execute(
                text(
                    """
                    INSERT INTO match_observation (
                        source, source_listing_id, observed_date, ingested_at,
                        decision, match_confidence, rule_version,
                        matched_entity_type, matched_entity_id, matched_subject_variant,
                        detected_set_code, detected_card_number, detected_variant, detected_grade,
                        features_blob_key, job_run_id
                    ) VALUES (
                        :source, :sid, :od, now(),
                        :decision, :mc, :rv,
                        :met, :mei, :msv,
                        :dsc, :dcn, :dv, :dg,
                        :fbk, :jrid
                    )
                    ON CONFLICT (observed_date, source, source_listing_id) DO NOTHING
                    """
                ),
                {
                    "source": _SOURCE,
                    "sid": listing.source_listing_id,
                    "od": as_of_date,
                    "decision": obs["decision"],
                    "mc": obs["match_confidence"],
                    "rv": obs["rule_version"],
                    "met": obs["matched_entity_type"],
                    "mei": obs["matched_entity_id"],
                    "msv": obs["matched_subject_variant"],
                    "dsc": obs["detected_set_code"],
                    "dcn": obs["detected_card_number"],
                    "dv": obs["detected_variant"],
                    "dg": obs["detected_grade"],
                    "fbk": features_key,
                    "jrid": job_run_id,
                },
            )
            s.commit()

    def _persist_flow_snapshots(
        self,
        per_group: dict[tuple[str, int, str], list[RawListing]],
        overmatch: dict[tuple[str, int, str], int],
        discarded: dict[tuple[str, int, str], int],
        as_of_date: date,
        job_run_id: int,
    ) -> int:
        if not per_group:
            return 0
        rows: list[dict[str, Any]] = []
        for (etype, eid, subject), listings in per_group.items():
            prices = [float(listing.price) for listing in listings]
            prices_sorted = sorted(prices)
            lowest_5 = prices_sorted[:5]
            rows.append(
                {
                    "observed_date": as_of_date,
                    "entity_type": etype,
                    "entity_id": eid,
                    "subject_variant": subject,
                    "active_listings": len(listings),
                    "new_listings": len(listings),  # refined by day-over-day diff in features
                    "estimated_disappeared_count": 0,
                    "avg_listing_price": Decimal(str(round(mean(prices), 2))),
                    "median_listing_price": Decimal(str(round(median(prices), 2))),
                    "price_band_json": _json(
                        {
                            "lowest_5_avg": round(sum(lowest_5) / max(len(lowest_5), 1), 2),
                            "p25": prices_sorted[len(prices_sorted) // 4] if prices_sorted else 0,
                            "p50": median(prices),
                            "p75": prices_sorted[3 * len(prices_sorted) // 4]
                            if prices_sorted
                            else 0,
                        }
                    ),
                    "avg_days_active": None,
                    "overmatch_count": overmatch.get((etype, eid, subject), 0),
                    "discarded_count": discarded.get((etype, eid, subject), 0),
                    "match_rules_version": RULE_VERSION,
                    "data_quality_score": 0.65,
                    "job_run_id": job_run_id,
                }
            )

        with session_owner() as s:
            stmt = text(
                """
                INSERT INTO listing_flow_snapshot (
                    observed_date, entity_type, entity_id, subject_variant,
                    active_listings, new_listings, estimated_disappeared_count,
                    avg_listing_price, median_listing_price, price_band_json,
                    avg_days_active, overmatch_count, discarded_count,
                    match_rules_version, data_quality_score, ingested_at, job_run_id
                ) VALUES (
                    :observed_date, :entity_type, :entity_id, :subject_variant,
                    :active_listings, :new_listings, :estimated_disappeared_count,
                    :avg_listing_price, :median_listing_price, CAST(:price_band_json AS JSONB),
                    :avg_days_active, :overmatch_count, :discarded_count,
                    :match_rules_version, :data_quality_score, now(), :job_run_id
                )
                ON CONFLICT (observed_date, entity_type, entity_id, subject_variant)
                DO NOTHING
                """
            )
            for row in rows:
                s.execute(stmt, row)
            s.commit()
        return len(rows)


def _json(obj: Any) -> str:
    import json as _j

    return _j.dumps(obj, default=str, sort_keys=True)


def _dev_fixture_listings() -> list[dict[str, Any]]:
    return [
        # Charizard SAR raw — 4 listings at varying prices
        {
            "source_listing_id": "ebay-001",
            "title": "Pokemon Charizard ex SAR 199/197 Obsidian Flames NM",
            "price": "440.00",
            "currency": "USD",
        },
        {
            "source_listing_id": "ebay-002",
            "title": "CHARIZARD EX 199/197 Obsidian Flames Special Illustration Rare",
            "price": "475.00",
            "currency": "USD",
        },
        {
            "source_listing_id": "ebay-003",
            "title": "Charizard ex 199/197 Obsidian Flames SAR near mint",
            "price": "460.00",
            "currency": "USD",
        },
        # Charizard PSA 10
        {
            "source_listing_id": "ebay-010",
            "title": "Charizard ex 199/197 Obsidian Flames SAR PSA 10 Gem Mint",
            "price": "1750.00",
            "currency": "USD",
        },
        {
            "source_listing_id": "ebay-011",
            "title": "PSA 10 Charizard ex Special Illustration 199/197 Obsidian Flames",
            "price": "1800.00",
            "currency": "USD",
        },
        # Pikachu SIR raw
        {
            "source_listing_id": "ebay-020",
            "title": "Pikachu ex SIR 238/191 Surging Sparks Secret Rare NM",
            "price": "860.00",
            "currency": "USD",
        },
        {
            "source_listing_id": "ebay-021",
            "title": "Pokemon Pikachu ex Secret Rare 238/191 Surging Sparks",
            "price": "845.00",
            "currency": "USD",
        },
        # Umbreon Moonbreon raw
        {
            "source_listing_id": "ebay-030",
            "title": "Umbreon VMAX Alt Art 215/203 Evolving Skies Moonbreon NM",
            "price": "820.00",
            "currency": "USD",
        },
        {
            "source_listing_id": "ebay-031",
            "title": "Moonbreon Umbreon VMAX Alternate Art 215/203 Evolving Skies",
            "price": "810.00",
            "currency": "USD",
        },
        # Sealed: Surging Sparks Booster Box
        {
            "source_listing_id": "ebay-040",
            "title": "Pokemon Surging Sparks Booster Box Factory Sealed English",
            "price": "190.00",
            "currency": "USD",
        },
        {
            "source_listing_id": "ebay-041",
            "title": "Surging Sparks Booster Box Sealed Pokemon TCG English 36 packs",
            "price": "195.00",
            "currency": "USD",
        },
        # Rejected: Japanese
        {
            "source_listing_id": "ebay-050",
            "title": "Japanese Pikachu ex SIR 238/191 Surging Sparks",
            "price": "500.00",
            "currency": "USD",
        },
        # Rejected: proxy
        {
            "source_listing_id": "ebay-051",
            "title": "Charizard ex 199/197 Obsidian Flames SAR custom proxy",
            "price": "12.00",
            "currency": "USD",
        },
    ]
