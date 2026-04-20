"""Feature engine. PIT-enforced via the feature_compute DB role + *_asof() functions.

Do NOT read base snapshot tables directly from any code in this package. Every read
goes through `as_of_filter` → SECURITY DEFINER functions. A CI grep check fails the
build if any feature file references `price_snapshot_daily` (or any other base table)
outside of the allow-list in `as_of.py`.
"""

FEATURE_SET_VERSION = "1.0.0"

from miami_features.as_of import (  # noqa: E402
    graded_snapshot_asof,
    listing_flow_asof,
    population_snapshot_asof,
    price_snapshot_asof,
    sealed_snapshot_asof,
)
from miami_features.build import build_features  # noqa: E402

__all__ = [
    "FEATURE_SET_VERSION",
    "build_features",
    "graded_snapshot_asof",
    "listing_flow_asof",
    "population_snapshot_asof",
    "price_snapshot_asof",
    "sealed_snapshot_asof",
]
