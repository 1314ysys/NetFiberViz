"""画布布局持久化。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.db import get_db
from app.models import CanvasLayout, Room
from app.services.perms import assert_room

router = APIRouter(prefix="/canvas", tags=["canvas"])


class CanvasIn(BaseModel):
    data_json: dict


@router.get("/{room_id}")
async def get_canvas(room_id: int, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(CanvasLayout).where(CanvasLayout.room_id == room_id))).scalar_one_or_none()
    if not row:
        return {"room_id": room_id, "data_json": None}
    return {"room_id": room_id, "data_json": row.data_json, "updated_at": row.updated_at.isoformat()}


@router.put("/{room_id}")
async def put_canvas(room_id: int, body: CanvasIn, db: AsyncSession = Depends(get_db),
                     user=Depends(get_current_user)):
    await assert_room(db, user, room_id)
    row = (await db.execute(select(CanvasLayout).where(CanvasLayout.room_id == room_id))).scalar_one_or_none()
    if not row:
        row = CanvasLayout(room_id=room_id)
        db.add(row)
    row.data_json = body.data_json
    await db.commit()
    return {"ok": True}
