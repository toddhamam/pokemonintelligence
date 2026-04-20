"""Per-source ingestion. Each collector is:
- idempotent (insert-only with ON CONFLICT DO NOTHING on content_hash PK)
- dev-mode aware (returns fixture payloads when MIAMI_DEV_MODE=1)
- archive-first (writes raw payload to Blob before parse)
- observable (writes start/end rows to job_runs)
"""

from miami_collectors.base import BaseCollector, CollectorResult
from miami_collectors.blob_archive import archive_payload

__all__ = ["BaseCollector", "CollectorResult", "archive_payload"]
