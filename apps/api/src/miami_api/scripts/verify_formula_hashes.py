"""CI script: assert each scoring_formula DB row's content_hash matches the YAML
in Git. Catches the case where a formula was edited without being re-mirrored into
the DB (which would silently change scoring behavior).

In v1 the DB mirror is populated by this same script the first time it runs; on
subsequent runs it verifies rather than inserts.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from miami_common.db import session_owner
from miami_common.logging import configure_logging, get_logger
from miami_scoring.formula_loader import load_active_formulas


def main() -> int:
    configure_logging()
    log = get_logger(__name__)
    active = load_active_formulas()

    mismatches: list[str] = []
    with session_owner() as s:
        for formula in (active.breakout, active.arbitrage, active.long_term):
            existing = s.execute(
                text("SELECT content_hash FROM scoring_formula WHERE name=:n AND version=:v"),
                {"n": formula.name, "v": formula.version},
            ).scalar_one_or_none()

            if existing is None:
                s.execute(
                    text(
                        """
                        INSERT INTO scoring_formula
                          (name, version, git_sha, content_hash, definition_yaml, activated_at)
                        VALUES (:n, :v, :sha, :hash, :yaml, now())
                        """
                    ),
                    {
                        "n": formula.name,
                        "v": formula.version,
                        "sha": _git_sha(),
                        "hash": formula.content_hash,
                        "yaml": formula.raw_yaml,
                    },
                )
                log.info("formula_mirrored", name=formula.name, version=formula.version)
            elif existing != formula.content_hash:
                mismatches.append(
                    f"{formula.name}@{formula.version}: DB {existing[:12]}... vs Git {formula.content_hash[:12]}..."
                )
        s.commit()

    if mismatches:
        print("Formula content_hash mismatches — bump version and re-mirror:", file=sys.stderr)
        for m in mismatches:
            print(f"  - {m}", file=sys.stderr)
        return 1
    log.info("formula_hashes_verified")
    return 0


def _git_sha() -> str:
    import subprocess

    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
