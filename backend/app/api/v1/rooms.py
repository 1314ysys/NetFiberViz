"""rooms（支持层级树）/ racks，含权限校验。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import Device, Rack, Room, User
from app.services.audit import audit
from app.services.perms import assert_rack, assert_room, require_core

router = APIRouter(tags=["rooms"])


class RoomIn(BaseModel):
    name: str
    code: str
    address: str = ""
    parent_id: int | None = None


class RackIn(BaseModel):
    room_id: int
    name: str
    code: str
    u_count: int = 42
    pos_x: float = 0
    pos_y: float = 0
    group_id: str | None = None


def _serialize(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


async def _descendants(db: AsyncSession, room_id: int) -> set[int]:
    rows = (await db.execute(select(Room.id, Room.parent_id))).all()
    children: dict[int, list[int]] = {}
    for rid, pid in rows:
        children.setdefault(pid, []).append(rid)
    out: set[int] = set()
    stack = [room_id]
    while stack:
        cur = stack.pop()
        for c in children.get(cur, []):
            if c not in out:
                out.add(c)
                stack.append(c)
    return out


# ---------------- rooms ----------------
@router.get("/rooms")
async def list_rooms(db: AsyncSession = Depends(get_db)):
    """返回全部机房（扁平，含 parent_id，前端自行组树）。读操作对所有登录用户开放。"""
    return [_serialize(r) for r in (await db.execute(select(Room).order_by(Room.id))).scalars()]


@router.post("/rooms")
async def create_room(body: RoomIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if body.parent_id is None:
        # 顶层机房 = 核心机房，仅核心管理员可建
        await require_core(user)
    else:
        parent = (await db.execute(select(Room).where(Room.id == body.parent_id))).scalar_one_or_none()
        if not parent:
            raise HTTPException(404, "上级机房不存在")
        await assert_room(db, user, body.parent_id)
    if (await db.execute(select(Room).where(Room.code == body.code))).scalar_one_or_none():
        raise HTTPException(409, f"机房编码 {body.code} 已存在")
    room = Room(**body.model_dump())
    db.add(room)
    await db.flush()
    await audit(db, user.id, "room", room.id, "create", after=room)
    await db.commit()
    await db.refresh(room)
    return _serialize(room)


@router.put("/rooms/{room_id}")
async def update_room(room_id: int, body: RoomIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    room = (await db.execute(select(Room).where(Room.id == room_id))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "机房不存在")
    await assert_room(db, user, room_id)

    if body.parent_id != room.parent_id:
        # 变更归属：不能挂到自己或自己的子孙下（防环），且需要新上级的写权限
        if body.parent_id is not None:
            if body.parent_id == room_id:
                raise HTTPException(400, "不能将机房挂到自身之下")
            if body.parent_id in await _descendants(db, room_id):
                raise HTTPException(400, "不能将机房挂到自己的子机房之下")
            if not (await db.execute(select(Room).where(Room.id == body.parent_id))).scalar_one_or_none():
                raise HTTPException(404, "上级机房不存在")
            await assert_room(db, user, body.parent_id)
        else:
            # 提升为顶层机房，仅核心管理员
            await require_core(user)

    before = Room(**_serialize(room))
    for k, v in body.model_dump().items():
        setattr(room, k, v)
    await audit(db, user.id, "room", room.id, "update", before=before, after=room)
    await db.commit()
    return _serialize(room)


@router.delete("/rooms/{room_id}")
async def delete_room(room_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    room = (await db.execute(select(Room).where(Room.id == room_id))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "机房不存在")
    await assert_room(db, user, room_id)
    if (await db.execute(select(Room).where(Room.parent_id == room_id))).scalar_one_or_none():
        raise HTTPException(409, "机房下存在子机房，禁止删除")
    if (await db.execute(select(Rack).where(Rack.room_id == room_id))).scalar_one_or_none():
        raise HTTPException(409, "机房下存在机柜，禁止删除")
    await audit(db, user.id, "room", room.id, "delete", before=room)
    await db.delete(room)
    await db.commit()
    return {"ok": True}


# ---------------- racks ----------------
@router.get("/racks")
async def list_racks(room_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Rack)
    if room_id:
        q = q.where(Rack.room_id == room_id)
    return [_serialize(r) for r in (await db.execute(q)).scalars()]


@router.post("/racks")
async def create_rack(body: RackIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await assert_room(db, user, body.room_id)
    rack = Rack(**body.model_dump())
    db.add(rack)
    await db.flush()
    await audit(db, user.id, "rack", rack.id, "create", after=rack)
    await db.commit()
    await db.refresh(rack)
    return _serialize(rack)


@router.put("/racks/{rack_id}")
async def update_rack(rack_id: int, body: RackIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    rack = (await db.execute(select(Rack).where(Rack.id == rack_id))).scalar_one_or_none()
    if not rack:
        raise HTTPException(404, "机柜不存在")
    await assert_rack(db, user, rack_id)
    # 迁移到别的机房需要目标机房写权限
    if body.room_id != rack.room_id:
        await assert_room(db, user, body.room_id)
    before = Rack(**_serialize(rack))
    for k, v in body.model_dump().items():
        setattr(rack, k, v)
    await audit(db, user.id, "rack", rack.id, "update", before=before, after=rack)
    await db.commit()
    return _serialize(rack)


@router.delete("/racks/{rack_id}")
async def delete_rack(rack_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rack = (await db.execute(select(Rack).where(Rack.id == rack_id))).scalar_one_or_none()
    if not rack:
        raise HTTPException(404, "机柜不存在")
    await assert_rack(db, user, rack_id)
    if (await db.execute(select(Device).where(Device.rack_id == rack_id))).scalar_one_or_none():
        raise HTTPException(409, "机柜下存在设备，禁止删除")
    await audit(db, user.id, "rack", rack.id, "delete", before=rack)
    await db.delete(rack)
    await db.commit()
    return {"ok": True}
