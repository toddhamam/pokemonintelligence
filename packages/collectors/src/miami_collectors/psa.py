"""PSA public API — population counts per (card, grade)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text

from miami_collectors.base import BaseCollector
from miami_common.db import session_owner
from miami_common.settings import get_settings


class PsaPopulationCollector(BaseCollector):
    source = "psa"
    target_table = "population_snapshot"
    pk_columns = ("observed_date", "card_id", "grade_company")
    has_content_hash = False  # population_snapshot PK is (observed_date, card_id, grade_company)

    def fetch(self, as_of_date: date) -> list[dict[str, Any]]:
        if get_settings().dev_mode:
            return _dev_fixture()
        raise NotImplementedError("Live PSA fetch not implemented in v1 scaffold")

    def parse(self, payload: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
        psa_to_card = _psa_to_card_map()
        rows: list[dict[str, Any]] = []
        for item in payload:
            psa_key = item.get("spec_id") or item.get("psa_key")
            card_id = psa_to_card.get(str(psa_key))
            if card_id is None:
                continue
            rows.append(
                {
                    "card_id": card_id,
                    "observed_date": as_of_date,
                    "grade_company": "PSA",
                    "total_population": int(item.get("total_population", 0)),
                    "grade_10_population": int(item.get("grade_10_population", 0)),
                    "grade_9_population": int(item.get("grade_9_population", 0)),
                }
            )
        return rows


def _psa_to_card_map() -> dict[str, int]:
    with session_owner() as s:
        return {
            row.psa_key: row.id
            for row in s.execute(
                text("SELECT id, psa_key FROM card WHERE psa_key IS NOT NULL")
            ).all()
        }


def _dev_fixture() -> list[dict[str, Any]]:
    return [
        {
            "spec_id": "psa-charizard-ex-sar-obf",
            "total_population": 3500,
            "grade_10_population": 1200,
            "grade_9_population": 1400,
        },
        {
            "spec_id": "psa-pikachu-ex-sir-sur",
            "total_population": 1800,
            "grade_10_population": 720,
            "grade_9_population": 650,
        },
        {
            "spec_id": "psa-umbreon-vmax-moon-evs",
            "total_population": 18500,
            "grade_10_population": 5200,
            "grade_9_population": 7800,
        },
    ]
