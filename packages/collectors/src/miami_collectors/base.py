"""Base class for all collectors.

Subclasses implement `fetch(as_of_date)` → list[dict] and `parse(payload, as_of_date)`
→ list of row dicts. The base class handles payload archival, job_runs bookkeeping,
content-hash computation, and insert-only persistence with ON CONFLICT DO NOTHING.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text

from miami_collectors.blob_archive import archive_payload
from miami_common.db import session_owner
from miami_common.logging import get_logger
from miami_common.time import utc_now

log = get_logger(__name__)


@dataclass(slots=True)
class CollectorResult:
    job_run_id: int
    rows_in: int
    rows_out: int
    status: str
    error: str | None = None


class BaseCollector(ABC):
    source: str
    target_table: str  # snapshot table this collector writes into
    pk_columns: tuple[str, ...]  # for ON CONFLICT DO NOTHING
    # True when the target table has a content_hash column (price/graded/sealed snapshots).
    # Population and retail-stock snapshots do NOT, so subclasses set this to False.
    has_content_hash: bool = True

    @abstractmethod
    def fetch(self, as_of_date: date) -> list[dict[str, Any]]:
        """Return the raw payload rows. Implementations pull from HTTP or fixtures."""

    @abstractmethod
    def parse(self, payload: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
        """Transform raw payload into canonical snapshot rows ready to insert."""

    def run(self, as_of_date: date) -> CollectorResult:
        params = {"as_of_date": as_of_date.isoformat()}
        with session_owner() as s:
            job_run_id = s.execute(
                text(
                    "INSERT INTO job_runs (job_name, started_at, status, params) "
                    "VALUES (:job, now(), 'running', CAST(:params AS JSONB)) RETURNING id"
                ),
                {"job": f"collector.{self.source}", "params": json.dumps(params)},
            ).scalar_one()
            s.commit()

        rows_in = 0
        rows_out = 0
        status = "success"
        error: str | None = None
        try:
            payload = self.fetch(as_of_date)
            rows_in = len(payload)
            blob_key = archive_payload(self.source, as_of_date, payload)
            log.info("collector_fetched", source=self.source, rows_in=rows_in, blob_key=blob_key)

            rows = self.parse(payload, as_of_date)
            # Inject ingested_at, job_run_id, and content_hash if missing.
            now = utc_now()
            for r in rows:
                r.setdefault("ingested_at", now)
                r["job_run_id"] = job_run_id
                if self.has_content_hash and "content_hash" not in r:
                    r["content_hash"] = _hash_row(r)
            rows_out = self._persist(rows)
            log.info("collector_persisted", source=self.source, rows_out=rows_out)
        except Exception as exc:
            status = "error"
            error = repr(exc)
            log.exception("collector_failed", source=self.source)

        with session_owner() as s:
            s.execute(
                text(
                    "UPDATE job_runs SET finished_at=now(), status=:status, "
                    "rows_in=:rows_in, rows_out=:rows_out, error_text=:error "
                    "WHERE id=:id"
                ),
                {
                    "status": status,
                    "rows_in": rows_in,
                    "rows_out": rows_out,
                    "error": error,
                    "id": job_run_id,
                },
            )
            s.commit()

        return CollectorResult(
            job_run_id=job_run_id,
            rows_in=rows_in,
            rows_out=rows_out,
            status=status,
            error=error,
        )

    def _persist(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        columns = list(rows[0].keys())
        col_list = ", ".join(columns)
        val_list = ", ".join(f":{c}" for c in columns)
        # ON CONFLICT DO NOTHING against the snapshot's composite PK — re-ingesting
        # identical data is a no-op.
        stmt = text(
            f"INSERT INTO {self.target_table} ({col_list}) VALUES ({val_list}) "
            f"ON CONFLICT DO NOTHING"
        )
        with session_owner() as s:
            for row in rows:
                s.execute(stmt, row)
            s.commit()
        return len(rows)


def _hash_row(row: dict[str, Any]) -> str:
    """Deterministic hash of business-relevant fields (excluding ingest timestamps)."""
    ignored = {"ingested_at", "job_run_id", "content_hash"}
    normalized = {k: _normalize(v) for k, v in row.items() if k not in ignored}
    payload = json.dumps(normalized, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def _normalize(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
