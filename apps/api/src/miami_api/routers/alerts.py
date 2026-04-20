from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from miami_api.auth import require_clerk_user
from miami_common.db import session_app
from miami_domain.schemas import AlertIn, AlertOut, AlertRule

router = APIRouter(tags=["alerts"], dependencies=[Depends(require_clerk_user)])


@router.post("/alerts", response_model=AlertOut)
def create_alert(
    body: AlertIn,
    user_id: str = Depends(require_clerk_user),
) -> AlertOut:
    with session_app() as s:
        new_id = s.execute(
            text(
                """
                INSERT INTO alert (user_id, name, rule_json, channel, active)
                VALUES (:uid, :name, CAST(:rule AS JSONB), :channel, TRUE)
                RETURNING id
                """
            ),
            {
                "uid": user_id,
                "name": body.name,
                "rule": json.dumps(body.rule.model_dump()),
                "channel": body.rule.channel,
            },
        ).scalar_one()
        s.commit()
    return AlertOut(id=int(new_id), name=body.name, rule=body.rule, active=True, last_fired_at=None)


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(user_id: str = Depends(require_clerk_user)) -> list[AlertOut]:
    with session_app() as s:
        rows = (
            s.execute(
                text(
                    "SELECT id, name, rule_json, active, last_fired_at "
                    "FROM alert WHERE user_id=:uid ORDER BY id DESC"
                ),
                {"uid": user_id},
            )
            .mappings()
            .all()
        )
    out: list[AlertOut] = []
    for r in rows:
        out.append(
            AlertOut(
                id=int(r["id"]),
                name=r["name"],
                rule=AlertRule(**r["rule_json"]),
                active=bool(r["active"]),
                last_fired_at=r["last_fired_at"].isoformat() if r["last_fired_at"] else None,
            )
        )
    return out


@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: int, user_id: str = Depends(require_clerk_user)) -> None:
    with session_app() as s:
        deleted = s.execute(
            text("DELETE FROM alert WHERE id=:id AND user_id=:uid"),
            {"id": alert_id, "uid": user_id},
        ).rowcount
        s.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")
