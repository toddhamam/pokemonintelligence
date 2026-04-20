"""Three separate engines to enforce role separation at connection time.

- `engine_owner`  runs migrations; owns tables and SECURITY DEFINER functions.
- `engine_app`    serves the API; can read snapshots and write user-scoped tables.
- `engine_feature_compute` runs feature/scoring jobs; can ONLY invoke `*_asof(p_as_of_date)`
  SECURITY DEFINER functions. SELECT on base snapshot tables is revoked for this role.

If a feature job accidentally tries to SELECT directly from `price_snapshot_daily`, the
query fails at the DB layer — this is the primary point-in-time enforcement.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from miami_common.settings import get_settings

_engines: dict[str, Engine] = {}


def _get_engine(url: str) -> Engine:
    if url not in _engines:
        _engines[url] = create_engine(url, pool_pre_ping=True, future=True)
    return _engines[url]


def engine_owner() -> Engine:
    return _get_engine(get_settings().db_url_owner)


def engine_app() -> Engine:
    return _get_engine(get_settings().db_url_app)


def engine_feature_compute() -> Engine:
    return _get_engine(get_settings().db_url_feature_compute)


@contextmanager
def session_app() -> Iterator[Session]:
    with sessionmaker(bind=engine_app(), expire_on_commit=False)() as s:
        yield s


@contextmanager
def session_owner() -> Iterator[Session]:
    with sessionmaker(bind=engine_owner(), expire_on_commit=False)() as s:
        yield s


@contextmanager
def session_feature_compute() -> Iterator[Session]:
    with sessionmaker(bind=engine_feature_compute(), expire_on_commit=False)() as s:
        yield s
