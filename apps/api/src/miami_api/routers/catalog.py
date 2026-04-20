from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from miami_common.db import session_app
from miami_domain.schemas import CardOut, Page, SealedProductOut, SetOut

router = APIRouter(tags=["catalog"])


@router.get("/sets", response_model=Page[SetOut])
def list_sets(limit: int = Query(default=50, ge=1, le=200)) -> Page[SetOut]:
    with session_app() as s:
        rows = (
            s.execute(
                text(
                    "SELECT id, name, series, language, release_date, set_type FROM set ORDER BY release_date DESC NULLS LAST LIMIT :l"
                ),
                {"l": limit},
            )
            .mappings()
            .all()
        )
    return Page[SetOut](items=[SetOut(**dict(r)) for r in rows])


@router.get("/sets/{set_id}", response_model=SetOut)
def get_set(set_id: int) -> SetOut:
    with session_app() as s:
        row = (
            s.execute(
                text(
                    "SELECT id, name, series, language, release_date, set_type FROM set WHERE id=:id"
                ),
                {"id": set_id},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return SetOut(**dict(row))


@router.get("/cards/{card_id}", response_model=CardOut)
def get_card(card_id: int) -> CardOut:
    with session_app() as s:
        row = (
            s.execute(
                text(
                    """
                SELECT id, set_id, name, card_number, rarity, pokemon_name, language,
                       is_promo, is_playable
                FROM card WHERE id=:id
                """
                ),
                {"id": card_id},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return CardOut(**dict(row))


@router.get("/sealed-products/{product_id}", response_model=SealedProductOut)
def get_sealed_product(product_id: int) -> SealedProductOut:
    with session_app() as s:
        row = (
            s.execute(
                text(
                    """
                SELECT id, set_id, product_name, product_type, msrp, exclusive_type
                FROM sealed_product WHERE id=:id
                """
                ),
                {"id": product_id},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return SealedProductOut(**dict(row))
