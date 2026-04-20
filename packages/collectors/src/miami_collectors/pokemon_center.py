"""Pokemon Center retail stock — in-stock state per sealed product.

Live implementation uses Playwright + residential egress; dev mode returns a static
fixture so the pipeline always has data to work with.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text

from miami_collectors.base import BaseCollector
from miami_common.db import session_owner
from miami_common.settings import get_settings
from miami_common.time import utc_now


class PokemonCenterStockCollector(BaseCollector):
    source = "pokemon_center"
    target_table = "retail_stock_snapshot"
    pk_columns = ("observed_date", "id")
    has_content_hash = False  # retail_stock_snapshot PK is (observed_date, id) only

    def fetch(self, as_of_date: date) -> list[dict[str, Any]]:
        if get_settings().dev_mode:
            return _dev_fixture()
        raise NotImplementedError("Live Pokemon Center scrape not implemented in v1 scaffold")

    def parse(self, payload: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
        url_to_product = _url_to_product_map()
        now = utc_now()
        rows: list[dict[str, Any]] = []
        for item in payload:
            product_id = url_to_product.get(item["official_url"])
            if product_id is None:
                continue
            rows.append(
                {
                    "sealed_product_id": product_id,
                    "retailer": "pokemon_center",
                    "observed_at": now,
                    "observed_date": as_of_date,
                    "in_stock": bool(item["in_stock"]),
                    "price": item.get("price"),
                    "restock_signal": item.get("restock_signal"),
                }
            )
        return rows


def _url_to_product_map() -> dict[str, int]:
    with session_owner() as s:
        return {
            row.official_url: row.id
            for row in s.execute(
                text("SELECT id, official_url FROM sealed_product WHERE official_url IS NOT NULL")
            ).all()
        }


def _dev_fixture() -> list[dict[str, Any]]:
    return [
        {
            "official_url": "https://www.pokemoncenter.com/product/sur-booster-box",
            "in_stock": False,
            "price": None,
            "restock_signal": "oos_7d",
        },
        {
            "official_url": "https://www.pokemoncenter.com/product/obf-etb",
            "in_stock": True,
            "price": 49.99,
            "restock_signal": None,
        },
    ]
