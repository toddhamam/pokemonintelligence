"""Dev-mode seed for the tiny tracked catalog used by fixtures and tests.

This is NOT the Phase 1 catalog-seeder. The production seeder (Phase 1) pulls from
pokemontcg.io and writes ~500 chase cards + ~50 sealed products. This script writes
exactly the 3 cards + 2 sealed products referenced by seed_rules.py and the eBay
fixture payload — enough for the pipeline to run end-to-end in dev.
"""

from __future__ import annotations

from sqlalchemy import text

from miami_common.db import session_owner
from miami_common.logging import configure_logging, get_logger


def main() -> None:
    configure_logging()
    log = get_logger(__name__)

    with session_owner() as s:
        # Sets
        s.execute(
            text(
                """
                INSERT INTO set (id, name, series, language, release_date, set_type, tcgplayer_group_id, has_booster_box)
                VALUES
                  (1, 'Obsidian Flames', 'Scarlet & Violet', 'en', '2023-08-11', 'standard', 23281, TRUE),
                  (2, 'Surging Sparks', 'Scarlet & Violet', 'en', '2024-11-08', 'standard', 24110, TRUE),
                  (3, 'Evolving Skies', 'Sword & Shield', 'en', '2021-08-27', 'standard', 2803, TRUE)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        # Cards (ids 1..3 match the seed_rules)
        s.execute(
            text(
                """
                INSERT INTO card
                  (id, set_id, tcgplayer_product_id, pricecharting_id, pokemontcg_id, psa_key,
                   name, card_number, rarity, sub_rarity, pokemon_name, language, is_promo, is_playable,
                   is_full_art, is_alt_art)
                VALUES
                  (1, 1, 515001, 'pc-charizard-ex-sar-obf', 'obf-199', 'psa-charizard-ex-sar-obf',
                   'Charizard ex', '199/197', 'Special Illustration Rare', 'SAR', 'Charizard', 'en', FALSE, FALSE,
                   TRUE, FALSE),
                  (2, 2, 521088, 'pc-pikachu-ex-sir-sur', 'sur-238', 'psa-pikachu-ex-sir-sur',
                   'Pikachu ex', '238/191', 'Special Illustration Rare', 'SIR', 'Pikachu', 'en', FALSE, FALSE,
                   TRUE, FALSE),
                  (3, 3, 245001, 'pc-umbreon-vmax-moon-evs', 'evs-215', 'psa-umbreon-vmax-moon-evs',
                   'Umbreon VMAX', '215/203', 'Alternate Art Secret', 'ALT', 'Umbreon', 'en', FALSE, FALSE,
                   FALSE, TRUE)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        # Sealed products (ids 10, 11 match seed_rules)
        s.execute(
            text(
                """
                INSERT INTO sealed_product
                  (id, set_id, tcgplayer_product_id, product_name, product_type, msrp, official_url, exclusive_type)
                VALUES
                  (10, 2, 560200, 'Surging Sparks Booster Box', 'booster_box', 161.64,
                   'https://www.pokemoncenter.com/product/sur-booster-box', NULL),
                  (11, 1, 540100, 'Obsidian Flames Elite Trainer Box', 'elite_trainer_box', 49.99,
                   'https://www.pokemoncenter.com/product/obf-etb', NULL)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        # Reset sequences so downstream inserts don't collide.
        s.execute(text("SELECT setval('set_id_seq', GREATEST(3, (SELECT MAX(id) FROM set)))"))
        s.execute(text("SELECT setval('card_id_seq', GREATEST(3, (SELECT MAX(id) FROM card)))"))
        s.execute(
            text(
                "SELECT setval('sealed_product_id_seq', "
                "GREATEST(11, (SELECT MAX(id) FROM sealed_product)))"
            )
        )
        s.commit()

    log.info("seed_catalog_complete")


if __name__ == "__main__":
    main()
