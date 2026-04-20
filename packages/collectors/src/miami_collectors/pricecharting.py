"""PriceCharting — primary transaction-truth source for raw + graded + sealed prices.

IMPORTANT: PriceCharting's API returns CURRENT values only — no historical prices or
realized sales. We accumulate our own daily-cadence history by calling this collector
once per day. Do not assume deeper history than days-since-launch.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import text

from miami_collectors.base import BaseCollector
from miami_common.db import session_owner
from miami_common.logging import get_logger
from miami_common.settings import get_settings

log = get_logger(__name__)

_SOURCE = "pricecharting"
_CONFIDENCE_BASELINE = 0.80


class PriceChartingRawCollector(BaseCollector):
    """Writes raw-card current prices into price_snapshot_daily."""

    source = _SOURCE
    target_table = "price_snapshot_daily"
    pk_columns = ("observed_date", "card_id", "source", "content_hash")

    def fetch(self, as_of_date: date) -> list[dict[str, Any]]:
        settings = get_settings()
        if settings.dev_mode:
            return _dev_fixture_raw()
        if not settings.pricecharting_api_key:
            raise RuntimeError("PRICECHARTING_API_KEY missing; cannot fetch live")
        # Live path: iterate over tracked cards with pricecharting_id populated.
        card_ids = _tracked_pricecharting_ids(kind="raw")
        out: list[dict[str, Any]] = []
        with httpx.Client(timeout=20.0) as client:
            for pc_id in card_ids:
                resp = client.get(
                    "https://www.pricecharting.com/api/product",
                    params={"t": settings.pricecharting_api_key, "id": pc_id},
                )
                resp.raise_for_status()
                out.append(resp.json())
        return out

    def parse(self, payload: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
        pc_to_card = _pc_to_card_map()
        rows: list[dict[str, Any]] = []
        for item in payload:
            pc_id = item.get("id") or item.get("pricecharting_id")
            card_id = pc_to_card.get(str(pc_id))
            if card_id is None:
                log.warning("pricecharting_unknown_id", pc_id=pc_id)
                continue
            rows.append(
                {
                    "card_id": card_id,
                    "observed_date": as_of_date,
                    "source": _SOURCE,
                    "source_record_id": str(pc_id),
                    "market_price": _cents(item.get("loose-price")),
                    "low_price": _cents(item.get("loose-price-1")),
                    "mid_price": _cents(item.get("loose-price-2")),
                    "high_price": _cents(item.get("loose-price-3")),
                    "near_mint_price": _cents(item.get("loose-price")),
                    "modeled_price": None,
                    "currency": "USD",
                    "confidence": _CONFIDENCE_BASELINE,
                }
            )
        return rows


class PriceChartingGradedCollector(BaseCollector):
    """Writes graded current prices (PSA 9, PSA 10) into graded_snapshot_daily."""

    source = _SOURCE
    target_table = "graded_snapshot_daily"
    pk_columns = ("observed_date", "card_id", "source", "grade_company", "grade", "content_hash")

    def fetch(self, as_of_date: date) -> list[dict[str, Any]]:
        if get_settings().dev_mode:
            return _dev_fixture_graded()
        # Live path same shape as raw — PriceCharting returns graded prices on same object.
        return PriceChartingRawCollector().fetch(as_of_date)

    def parse(self, payload: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
        pc_to_card = _pc_to_card_map()
        rows: list[dict[str, Any]] = []
        for item in payload:
            pc_id = item.get("id") or item.get("pricecharting_id")
            card_id = pc_to_card.get(str(pc_id))
            if card_id is None:
                continue
            # PSA 9
            p9 = _cents(item.get("graded-price-psa-9") or item.get("new-price"))
            if p9 is not None:
                rows.append(
                    {
                        "card_id": card_id,
                        "observed_date": as_of_date,
                        "source": _SOURCE,
                        "grade_company": "PSA",
                        "grade": "9",
                        "source_record_id": str(pc_id),
                        "market_price": p9,
                        "low_price": None,
                        "high_price": None,
                        "modeled_price": None,
                        "currency": "USD",
                        "confidence": _CONFIDENCE_BASELINE,
                    }
                )
            # PSA 10
            p10 = _cents(
                item.get("graded-price-psa-10")
                or item.get("manual-only-price")
                or item.get("box-only-price")
            )
            if p10 is not None:
                rows.append(
                    {
                        "card_id": card_id,
                        "observed_date": as_of_date,
                        "source": _SOURCE,
                        "grade_company": "PSA",
                        "grade": "10",
                        "source_record_id": str(pc_id),
                        "market_price": p10,
                        "low_price": None,
                        "high_price": None,
                        "modeled_price": None,
                        "currency": "USD",
                        "confidence": _CONFIDENCE_BASELINE,
                    }
                )
        return rows


# ---------- helpers ----------


def _cents(value: Any) -> Decimal | None:
    """PriceCharting historically returned prices in cents. Normalize to dollars."""
    if value is None:
        return None
    try:
        as_int = int(value)
        return Decimal(as_int) / Decimal(100)
    except (TypeError, ValueError):
        try:
            return Decimal(str(value))
        except Exception:
            return None


def _pc_to_card_map() -> dict[str, int]:
    with session_owner() as s:
        return {
            row.pricecharting_id: row.id
            for row in s.execute(
                text("SELECT id, pricecharting_id FROM card WHERE pricecharting_id IS NOT NULL")
            ).all()
        }


def _tracked_pricecharting_ids(kind: str) -> list[str]:
    with session_owner() as s:
        return [
            r.pricecharting_id
            for r in s.execute(
                text("SELECT pricecharting_id FROM card WHERE pricecharting_id IS NOT NULL")
            ).all()
        ]


# ---------- dev fixtures ----------


def _dev_fixture_raw() -> list[dict[str, Any]]:
    return [
        {"id": "pc-charizard-ex-sar-obf", "loose-price": 45000},
        {"id": "pc-pikachu-ex-sir-sur", "loose-price": 85000},
        {"id": "pc-umbreon-vmax-moon-evs", "loose-price": 82000},
    ]


def _dev_fixture_graded() -> list[dict[str, Any]]:
    return [
        {
            "id": "pc-charizard-ex-sar-obf",
            "graded-price-psa-9": 90000,
            "graded-price-psa-10": 175000,
        },
        {
            "id": "pc-pikachu-ex-sir-sur",
            "graded-price-psa-9": 160000,
            "graded-price-psa-10": 310000,
        },
        {
            "id": "pc-umbreon-vmax-moon-evs",
            "graded-price-psa-9": 155000,
            "graded-price-psa-10": 280000,
        },
    ]
