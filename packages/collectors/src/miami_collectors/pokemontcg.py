"""Pokémon TCG API (pokemontcg.io) — raw-card current-price anchor only.

Per Codex review: this is NOT a graded/sealed history source. It exposes TCGplayer-
aggregated current prices on card objects. Writes only into price_snapshot_daily.
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

_SOURCE = "pokemontcg"
_CONFIDENCE_BASELINE = 0.75


class PokemonTcgCollector(BaseCollector):
    source = _SOURCE
    target_table = "price_snapshot_daily"
    pk_columns = ("observed_date", "card_id", "source", "content_hash")

    def fetch(self, as_of_date: date) -> list[dict[str, Any]]:
        settings = get_settings()
        if settings.dev_mode:
            return _dev_fixture()
        ids = _tracked_pokemontcg_ids()
        out: list[dict[str, Any]] = []
        headers = {"X-Api-Key": settings.pokemontcg_api_key} if settings.pokemontcg_api_key else {}
        with httpx.Client(timeout=20.0, headers=headers) as client:
            for pid in ids:
                resp = client.get(f"https://api.pokemontcg.io/v2/cards/{pid}")
                resp.raise_for_status()
                body = resp.json().get("data")
                if body:
                    out.append(body)
        return out

    def parse(self, payload: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
        id_to_card = _pokemontcg_to_card_map()
        rows: list[dict[str, Any]] = []
        for item in payload:
            pid = item.get("id")
            card_id = id_to_card.get(str(pid))
            if card_id is None:
                continue
            # pokemontcg.io `tcgplayer.prices` is a dict of {finish_category: {low,mid,high,market}}
            prices = (item.get("tcgplayer") or {}).get("prices") or {}
            # Prefer holofoil/normal depending on which is populated.
            candidate = (
                prices.get("holofoil") or prices.get("normal") or next(iter(prices.values()), {})
            )
            rows.append(
                {
                    "card_id": card_id,
                    "observed_date": as_of_date,
                    "source": _SOURCE,
                    "source_record_id": str(pid),
                    "market_price": _to_decimal(candidate.get("market")),
                    "low_price": _to_decimal(candidate.get("low")),
                    "mid_price": _to_decimal(candidate.get("mid")),
                    "high_price": _to_decimal(candidate.get("high")),
                    "near_mint_price": _to_decimal(candidate.get("market")),
                    "modeled_price": None,
                    "currency": "USD",
                    "confidence": _CONFIDENCE_BASELINE,
                }
            )
        return rows


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _pokemontcg_to_card_map() -> dict[str, int]:
    with session_owner() as s:
        return {
            row.pokemontcg_id: row.id
            for row in s.execute(
                text("SELECT id, pokemontcg_id FROM card WHERE pokemontcg_id IS NOT NULL")
            ).all()
        }


def _tracked_pokemontcg_ids() -> list[str]:
    return list(_pokemontcg_to_card_map().keys())


def _dev_fixture() -> list[dict[str, Any]]:
    return [
        {
            "id": "obf-199",
            "tcgplayer": {
                "prices": {"holofoil": {"low": 400.0, "mid": 450.0, "high": 520.0, "market": 448.0}}
            },
        },
        {
            "id": "sur-238",
            "tcgplayer": {
                "prices": {"holofoil": {"low": 800.0, "mid": 870.0, "high": 920.0, "market": 855.0}}
            },
        },
        {
            "id": "evs-215",
            "tcgplayer": {
                "prices": {"holofoil": {"low": 780.0, "mid": 820.0, "high": 900.0, "market": 818.0}}
            },
        },
    ]
