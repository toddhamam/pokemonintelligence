"""As-of readers. These are the ONLY functions feature code uses to read snapshots.

Every function calls a SECURITY DEFINER table-valued function in Postgres
(`price_snapshot_asof(p_as_of_date)` etc.). The feature_compute DB role has EXECUTE
on those functions and NO SELECT on the base tables — so even if this module had a
bug, the DB would reject a direct read.

The allow-list below is the ONLY place in the `miami_features` package where
snapshot-adjacent SQL appears. CI grep enforces this.
"""

from __future__ import annotations

from datetime import date

import polars as pl
from sqlalchemy import text
from sqlalchemy.orm import Session

from miami_common.db import session_feature_compute


def _read(session: Session, sql: str, params: dict[str, object]) -> pl.DataFrame:
    result = session.execute(text(sql), params)
    rows = result.mappings().all()
    if not rows:
        return pl.DataFrame()
    return pl.from_dicts([dict(row) for row in rows])


def price_snapshot_asof(as_of_date: date) -> pl.DataFrame:
    with session_feature_compute() as s:
        return _read(
            s,
            "SELECT * FROM price_snapshot_asof(:d)",
            {"d": as_of_date},
        )


def graded_snapshot_asof(as_of_date: date) -> pl.DataFrame:
    with session_feature_compute() as s:
        return _read(
            s,
            "SELECT * FROM graded_snapshot_asof(:d)",
            {"d": as_of_date},
        )


def sealed_snapshot_asof(as_of_date: date) -> pl.DataFrame:
    with session_feature_compute() as s:
        return _read(
            s,
            "SELECT * FROM sealed_snapshot_asof(:d)",
            {"d": as_of_date},
        )


def listing_flow_asof(as_of_date: date) -> pl.DataFrame:
    with session_feature_compute() as s:
        return _read(
            s,
            "SELECT * FROM listing_flow_asof(:d)",
            {"d": as_of_date},
        )


def population_snapshot_asof(as_of_date: date) -> pl.DataFrame:
    with session_feature_compute() as s:
        return _read(
            s,
            "SELECT * FROM population_snapshot_asof(:d)",
            {"d": as_of_date},
        )
