"""Pytest config. PIT and matcher tests have different infra needs; this file
documents the split and marks DB-bound tests so CI runs them only when Postgres is up.
"""

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not os.environ.get("MIAMI_DB_URL_OWNER"):
        skip_db = pytest.mark.skip(reason="no DB configured")
        for item in items:
            if "db" in item.keywords:
                item.add_marker(skip_db)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "db: test requires a live Postgres matching .env")
