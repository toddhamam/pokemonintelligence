"""Archive raw payloads to Vercel Blob. Falls back to local filesystem in dev.

The DB tracks pointers in `payload_archive_index`; raw bytes live in object storage.
This split keeps the DB small while preserving everything we'd need for a matching
post-mortem.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text

from miami_common.db import session_owner
from miami_common.logging import get_logger
from miami_common.settings import get_settings
from miami_common.time import utc_now

log = get_logger(__name__)

_LOCAL_DIR = Path(".local/payload_archive")


def archive_payload(source: str, as_of_date: date, payload: Any) -> str:
    """Persist a payload and return the blob_key stored in payload_archive_index.

    The key includes a short random suffix so two collectors with the same `source`
    (e.g. PriceCharting raw + graded) running in the same second don't collide on
    the UNIQUE `payload_archive_index.blob_key` constraint.
    """
    now = utc_now()
    nonce = uuid.uuid4().hex[:8]
    blob_key = (
        f"{source}/{as_of_date.strftime('%Y%m')}/"
        f"{source}-{as_of_date.isoformat()}-{int(now.timestamp())}-{nonce}.json"
    )
    body = json.dumps(payload, default=str, sort_keys=True)
    size = len(body.encode())

    settings = get_settings()
    if settings.blob_read_write_token:
        # TODO(prod): upload via @vercel/blob HTTP API — see docs/runbook_collectors.md.
        # In v1 dev we never take this path because the token is empty.
        log.warning("blob_upload_not_implemented", blob_key=blob_key)
    else:
        path = _LOCAL_DIR / blob_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    with session_owner() as s:
        s.execute(
            text(
                "INSERT INTO payload_archive_index "
                "(source, fetched_at, blob_key, size_bytes, request_params) "
                "VALUES (:source, :fetched_at, :key, :size, CAST(:params AS JSONB))"
            ),
            {
                "source": source,
                "fetched_at": now,
                "key": blob_key,
                "size": size,
                "params": json.dumps({"as_of_date": as_of_date.isoformat()}),
            },
        )
        s.commit()
    return blob_key
