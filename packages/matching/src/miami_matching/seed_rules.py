"""Seed rules for the dev/test catalog.

In production, rules live in `match_rule` and are mirrored from Git; here we produce
an in-memory list for tests and dev runs. Matches the dev seed catalog in
apps/api/src/miami_api/scripts/seed_catalog_dev.py.

Expanding these rules to cover the full 500-card tracked universe is Phase 1 work.
"""

from __future__ import annotations

from miami_matching.engine import RuleDef


def default_seed_rules() -> list[RuleDef]:
    """Rules for the tiny dev catalog (see seed_catalog_dev.py for the matching entities)."""
    return [
        # --- Charizard ex SAR (Obsidian Flames 199/197) ---
        RuleDef(
            entity_type="card",
            entity_id=1,
            subject_variant="raw",
            include_terms=("charizard", "ex", "obsidian flames", "199/197"),
            exclude_terms=("lot", "proxy", "custom", "fake", "bundle", "break"),
            regex_patterns=(r"\bsar\b|special illustration",),
        ),
        RuleDef(
            entity_type="card",
            entity_id=1,
            subject_variant="psa10",
            include_terms=("charizard", "ex", "obsidian flames", "199/197"),
            exclude_terms=("lot", "proxy", "custom", "fake"),
            regex_patterns=(r"psa\s*10|gem mint",),
        ),
        RuleDef(
            entity_type="card",
            entity_id=1,
            subject_variant="psa9",
            include_terms=("charizard", "ex", "obsidian flames", "199/197"),
            exclude_terms=("lot", "proxy", "custom", "fake"),
            regex_patterns=(r"psa\s*9\b",),
        ),
        # --- Pikachu ex SIR (Surging Sparks 238/191) ---
        RuleDef(
            entity_type="card",
            entity_id=2,
            subject_variant="raw",
            include_terms=("pikachu", "ex", "surging sparks", "238/191"),
            exclude_terms=("lot", "proxy", "custom", "fake", "bundle", "japanese"),
            regex_patterns=(r"\bsir\b|secret",),
        ),
        RuleDef(
            entity_type="card",
            entity_id=2,
            subject_variant="psa10",
            include_terms=("pikachu", "ex", "surging sparks", "238/191"),
            exclude_terms=("lot", "proxy", "custom", "fake", "japanese"),
            regex_patterns=(r"psa\s*10|gem mint",),
        ),
        # --- Moonbreon / Umbreon VMAX alt art (Evolving Skies 215/203) ---
        RuleDef(
            entity_type="card",
            entity_id=3,
            subject_variant="raw",
            include_terms=("umbreon", "vmax", "evolving skies", "215/203"),
            exclude_terms=("lot", "proxy", "custom", "fake", "bundle", "japanese", "vstar"),
            regex_patterns=(r"alt(?:ernate)?\s*art|moonbreon",),
        ),
        RuleDef(
            entity_type="card",
            entity_id=3,
            subject_variant="psa10",
            include_terms=("umbreon", "vmax", "evolving skies", "215/203"),
            exclude_terms=("lot", "proxy", "custom", "fake", "japanese"),
            regex_patterns=(r"psa\s*10|gem mint",),
        ),
        # --- Surging Sparks booster box (sealed_product id=10) ---
        RuleDef(
            entity_type="sealed_product",
            entity_id=10,
            subject_variant="sealed",
            include_terms=("surging sparks", "booster box"),
            exclude_terms=(
                "empty",
                "display",
                "proxy",
                "japanese",
                "booster bundle",
                "etb",
                "elite trainer",
                "pack",
                "single",
            ),
        ),
        # --- Obsidian Flames ETB (sealed_product id=11) ---
        RuleDef(
            entity_type="sealed_product",
            entity_id=11,
            subject_variant="sealed",
            include_terms=("obsidian flames", "elite trainer box"),
            exclude_terms=(
                "empty",
                "display",
                "proxy",
                "japanese",
                "pokemon center",
                "booster bundle",
                "booster box",
            ),
        ),
    ]
