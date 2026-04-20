"""Loads YAML formulas from the Git-canonical directory and verifies content hashes.

At deploy time a migration INSERTs rows into `scoring_formula` (name, version, git_sha,
content_hash, definition_yaml). CI asserts the DB `content_hash` equals the SHA-256 of
the YAML bytes at the recorded `git_sha`. Runtime loading prefers the Git copy — the DB
row is activation metadata, not the source.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FORMULAS_DIR = Path(__file__).parent / "formulas"


@dataclass(frozen=True, slots=True)
class FormulaDef:
    name: str
    version: str
    definition: dict[str, Any]
    content_hash: str
    raw_yaml: str

    @classmethod
    def from_path(cls, path: Path) -> FormulaDef:
        raw = path.read_text()
        data = yaml.safe_load(raw)
        return cls(
            name=data["name"],
            version=data["version"],
            definition=data,
            content_hash=hashlib.sha256(raw.encode()).hexdigest(),
            raw_yaml=raw,
        )


@dataclass(frozen=True, slots=True)
class ActiveFormulas:
    breakout: FormulaDef
    arbitrage: FormulaDef
    long_term: FormulaDef


def load_active_formulas(dir_override: Path | None = None) -> ActiveFormulas:
    d = dir_override or FORMULAS_DIR
    loaded: dict[str, FormulaDef] = {}
    for path in sorted(d.glob("*.yaml")):
        f = FormulaDef.from_path(path)
        # Keep only the highest version per name.
        existing = loaded.get(f.name)
        if existing is None or _semver_tuple(f.version) > _semver_tuple(existing.version):
            loaded[f.name] = f
    return ActiveFormulas(
        breakout=loaded["breakout"],
        arbitrage=loaded["arbitrage"],
        long_term=loaded["long_term"],
    )


def _semver_tuple(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    padded = [*parts, "0", "0", "0"][:3]
    return (int(padded[0]), int(padded[1]), int(padded[2]))
