"""ODF 盘间连接（熔接/法兰直通）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.db import get_db
from app.models import Interconnect, OdfSlot, PatchCord, Port
from app.services.audit import audit, ensure_slot_free_for_interconnect, to_dict
from app.services.perms import assert_slot

router = APIRouter(prefix="/interconnects", tags=["interconnects"])


class InterconnectIn(BaseModel):
    slot_a_id: int
    slot_b_id: int
    kind: str  # splice | adapter
    remark: str = ""


@router.get("")
async def list_ic(db: AsyncSession = Depends(get_db)):
    return [to_dict(i) for i in (await db.execute(select(Interconnect))).scalars()]


@router.post("")
async def create_ic(body: InterconnectIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if body.kind not in ("splice", "adapter"):
        raise HTTPException(400, "kind 必须是 splice 或 adapter")
    if body.slot_a_id == body.slot_b_id:
        raise HTTPException(400, "两端不能是同一孔位")
    for sid in (body.slot_a_id, body.slot_b_id):
        if not (await db.execute(select(OdfSlot).where(OdfSlot.id == sid))).scalar_one_or_none():
            raise HTTPException(404, f"孔位 {sid} 不存在")
        await assert_slot(db, user, sid)
    await ensure_slot_free_for_interconnect(db, body.slot_a_id)
    await ensure_slot_free_for_interconnect(db, body.slot_b_id)
    ic = Interconnect(**body.model_dump(), created_by=user.id)
    db.add(ic)
    await db.flush()
    # 孔位状态置为 used（通过其 port）
    for sid in (body.slot_a_id, body.slot_b_id):
        slot = (await db.execute(select(OdfSlot).where(OdfSlot.id == sid))).scalar_one()
        port = (await db.execute(select(Port).where(Port.id == slot.port_id))).scalar_one()
        port.status = "used"
    await audit(db, user.id, "interconnect", ic.id, "create", after=ic)
    await db.commit()
    await db.refresh(ic)
    return to_dict(ic)


@router.delete("/{ic_id}")
async def delete_ic(ic_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    ic = (await db.execute(select(Interconnect).where(Interconnect.id == ic_id))).scalar_one_or_none()
    if not ic:
        raise HTTPException(404, "盘间连接不存在")
    for sid in (ic.slot_a_id, ic.slot_b_id):
        await assert_slot(db, user, sid)
        slot = (await db.execute(select(OdfSlot).where(OdfSlot.id == sid))).scalar_one_or_none()
        if slot:
            port = (await db.execute(select(Port).where(Port.id == slot.port_id))).scalar_one_or_none()
            if port and port.status == "used":
                # 若无在用跳纤则释放
                cord = (await db.execute(select(PatchCord).where(
                    PatchCord.status == "active",
                    (PatchCord.port_a_id == port.id) | (PatchCord.port_b_id == port.id)))).scalar_one_or_none()
                if not cord:
                    port.status = "free"
    await audit(db, user.id, "interconnect", ic.id, "delete", before=ic)
    await db.delete(ic)
    await db.commit()
    return {"ok": True}
