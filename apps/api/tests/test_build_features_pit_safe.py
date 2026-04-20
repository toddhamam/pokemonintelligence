"""PIT integration test. Injects a late-arriving raw row (ingested_at past the
12h cutoff) and verifies build_features(as_of_date) output is unchanged.

This is the test that proves feature construction is point-in-time safe. The DB role
+ SECURITY DEFINER *_asof function enforcement is the primary mechanism; this test
is the end-to-end proof.

Requires a running Postgres matching .env (see conftest.py — skipped otherwise).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from miami_common.db import session_owner
from miami_features import FEATURE_SET_VERSION, build_features

pytestmark = pytest.mark.db


def _wipe_card(card_id: int) -> None:
    with session_owner() as s:
        for tbl in (
            "feature_snapshot",
            "price_snapshot_daily",
        ):
            s.execute(
                text(
                    f"DELETE FROM {tbl} WHERE "
                    + (
                        "card_id = :cid"
                        if "card_id" in _columns(tbl)
                        else "entity_id = :cid AND entity_type='card'"
                    )
                ),
                {"cid": card_id},
            )
        s.commit()


def _columns(tbl: str) -> list[str]:
    with session_owner() as s:
        return [
            r[0]
            for r in s.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name=:t"),
                {"t": tbl},
            ).all()
        ]


def test_build_features_is_pit_safe() -> None:
    card_id = 1  # from seed_catalog_dev
    as_of_date = date(2026, 4, 10)

    _wipe_card(card_id)

    # Seed pre-cutoff rows.
    with session_owner() as s:
        for offset in range(7):
            s.execute(
                text(
                    """
                    INSERT INTO price_snapshot_daily
                      (card_id, observed_date, source, source_record_id, content_hash,
                       market_price, currency, confidence, ingested_at)
                    VALUES (
                       :cid, :od, 'pricecharting', 'seed', :hash,
                       100.0 + :offset, 'USD', 0.8, :od::timestamptz
                    )
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "cid": card_id,
                    "od": as_of_date - timedelta(days=offset),
                    "hash": f"pit-seed-{offset}",
                    "offset": float(offset),
                },
            )
        s.commit()

    # First build — canonical result.
    rows_before = build_features(as_of_date, FEATURE_SET_VERSION)
    card_feature_before = next(
        r for r in rows_before if r.entity_id == card_id and r.subject_variant == "raw"
    ).features_json

    # Inject a LATE-ARRIVING row: observed_date earlier, ingested_at well past the
    # cutoff (24 hours after as_of_date → past the 12h window).
    with session_owner() as s:
        s.execute(
            text(
                """
                INSERT INTO price_snapshot_daily
                  (card_id, observed_date, source, source_record_id, content_hash,
                   market_price, currency, confidence, ingested_at)
                VALUES (
                   :cid, :od, 'pricecharting', 'late', 'pit-late-inject',
                   9999.0, 'USD', 0.8, :ingested
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "cid": card_id,
                "od": as_of_date - timedelta(days=3),  # valid observed_date
                "ingested": as_of_date + timedelta(hours=24),  # past the 12h cutoff
            },
        )
        s.commit()

    # Rebuild — must be identical; the late row is filtered out by *_asof().
    rows_after = build_features(as_of_date, FEATURE_SET_VERSION)
    card_feature_after = next(
        r for r in rows_after if r.entity_id == card_id and r.subject_variant == "raw"
    ).features_json

    assert card_feature_before == card_feature_after, (
        "Late-arriving raw row leaked into features — PIT enforcement broken"
    )
