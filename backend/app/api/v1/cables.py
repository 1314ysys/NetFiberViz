"""光缆/纤芯：成端(landed→port)、芯对芯熔接(spliced)、状态管理。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.db import get_db
from app.models import Cable, Core, Port
from app.services.audit import audit, to_dict
from app.services.perms import assert_cable, assert_port, assert_room

router = APIRouter(tags=["cables"])


class CableIn(BaseModel):
    room_id: int
    name: str
    core_count: int = 24
    cable_type: str = "GYTA 单模"
    direction_from: str = ""
    remark: str = ""


class CoreLandIn(BaseModel):
    port_id: int | None = None


class CoreSpliceIn(BaseModel):
    peer_core_id: int


class CoreStatusIn(BaseModel):
    status: str  # unused/landed/spliced/spare/fault


@router.get("/cables")
async def list_cables(room_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Cable)
    if room_id:
        q = q.where(Cable.room_id == room_id)
    return [to_dict(c) for c in (await db.execute(q)).scalars()]


@router.post("/cables")
async def create_cable(body: CableIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await assert_room(db, user, body.room_id)
    cable = Cable(**body.model_dump())
    db.add(cable)
    await db.flush()
    for n in range(1, body.core_count + 1):
        db.add(Core(cable_id=cable.id, core_no=n))
    await audit(db, user.id, "cable", cable.id, "create", after=cable)
    await db.commit()
    await db.refresh(cable)
    return to_dict(cable)


@router.get("/cores")
async def list_cores(cable_id: int, db: AsyncSession = Depends(get_db)):
    cores = (await db.execute(select(Core).where(Core.cable_id == cable_id).order_by(Core.core_no))).scalars().all()
    out = []
    for c in cores:
        d = to_dict(c)
        if c.port_id:
            port = (await db.execute(select(Port).where(Port.id == c.port_id))).scalar_one_or_none()
            d["port"] = to_dict(port) if port else None
        if c.peer_core_id:
            peer = (await db.execute(select(Core).where(Core.id == c.peer_core_id))).scalar_one_or_none()
            d["peer_core"] = to_dict(peer) if peer else None
        out.append(d)
    return out


@router.put("/cores/{core_id}/land")
async def land_core(core_id: int, body: CoreLandIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    core = (await db.execute(select(Core).where(Core.id == core_id))).scalar_one_or_none()
    if not core:
        raise HTTPException(404, "纤芯不存在")
    await assert_cable(db, user, core.cable_id)
    if body.port_id:
        await assert_port(db, user, body.port_id)
    before = Core(**to_dict(core))
    if core.status == "landed" and core.port_id:
        old = (await db.execute(select(Port).where(Port.id == core.port_id))).scalar_one_or_none()
        if old and old.status == "used":
            old.status = "free"
    core.port_id = body.port_id
    core.status = "landed" if body.port_id else "unused"
    if body.port_id:
        port = (await db.execute(select(Port).where(Port.id == body.port_id))).scalar_one_or_none()
        if not port:
            raise HTTPException(404, "孔位端口不存在")
        port.status = "used"
    await audit(db, user.id, "core", core.id, "update", before=before, after=core, remark="纤芯成端")
    await db.commit()
    return to_dict(core)


@router.put("/cores/{core_id}/splice")
async def splice_core(core_id: int, body: CoreSpliceIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    core = (await db.execute(select(Core).where(Core.id == core_id))).scalar_one_or_none()
    peer = (await db.execute(select(Core).where(Core.id == body.peer_core_id))).scalar_one_or_none()
    if not core or not peer:
        raise HTTPException(404, "纤芯不存在")
    await assert_cable(db, user, core.cable_id)
    await assert_cable(db, user, peer.cable_id)
    if core.cable_id == peer.cable_id:
        raise HTTPException(400, "不能与同缆纤芯熔接")
    if peer.peer_core_id and peer.peer_core_id != core.id:
        raise HTTPException(409, f"纤芯 #{peer.id} 已与纤芯 #{peer.peer_core_id} 熔接")
    core.peer_core_id = peer.id
    core.status = "spliced"
    peer.peer_core_id = core.id
    peer.status = "spliced"
    await audit(db, user.id, "core", core.id, "update", after=core, remark=f"与芯#{peer.id}熔接")
    await audit(db, user.id, "core", peer.id, "update", after=peer, remark=f"与芯#{core.id}熔接")
    await db.commit()
    return to_dict(core)


@router.put("/cores/{core_id}/status")
async def set_core_status(core_id: int, body: CoreStatusIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if body.status not in ("unused", "landed", "spliced", "spare", "fault"):
        raise HTTPException(400, "非法纤芯状态")
    core = (await db.execute(select(Core).where(Core.id == core_id))).scalar_one_or_none()
    if not core:
        raise HTTPException(404, "纤芯不存在")
    await assert_cable(db, user, core.cable_id)
    before = Core(**to_dict(core))
    core.status = body.status
    await audit(db, user.id, "core", core.id, "update", before=before, after=core)
    await db.commit()
    return to_dict(core)


# ---------------- 批量熔接 ----------------
class SplicePair(BaseModel):
    core_a_id: int
    core_b_id: int


class BatchSpliceIn(BaseModel):
    pairs: list[SplicePair]


async def _core_or_none(db: AsyncSession, cid: int):
    return (await db.execute(select(Core).where(Core.id == cid))).scalar_one_or_none()


@router.post("/cores/batch-splice")
async def batch_splice(body: BatchSpliceIn, db: AsyncSession = Depends(get_db),
                       user=Depends(get_current_user)):
    """批量熔接：逐条校验并执行，返回成功/失败明细（不整体回滚）。

    熔接是物理事实，已完成的保留；调用方据 failed 列表补处理。
    """
    succeeded: list[dict] = []
    failed: list[dict] = []

    for pr in body.pairs:
        a = await _core_or_none(db, pr.core_a_id)
        b = await _core_or_none(db, pr.core_b_id)
        if not a or not b:
            failed.append({"a": pr.core_a_id, "b": pr.core_b_id, "reason": "纤芯不存在"})
            continue
        if a.cable_id == b.cable_id:
            failed.append({"a": pr.core_a_id, "b": pr.core_b_id, "reason": "同缆纤芯不能互熔"})
            continue
        if a.status == "spliced" or a.peer_core_id:
            failed.append({"a": pr.core_a_id, "b": pr.core_b_id,
                           "reason": f"芯 {a.core_no} 已熔接"})
            continue
        if b.status == "spliced" or b.peer_core_id:
            failed.append({"a": pr.core_a_id, "b": pr.core_b_id,
                           "reason": f"芯 {b.core_no} 已熔接"})
            continue
        try:
            await assert_cable(db, user, a.cable_id)
            await assert_cable(db, user, b.cable_id)
        except HTTPException as e:
            failed.append({"a": pr.core_a_id, "b": pr.core_b_id, "reason": str(e.detail)})
            continue

        a.peer_core_id = b.id
        a.status = "spliced"
        b.peer_core_id = a.id
        b.status = "spliced"
        await audit(db, user.id, "core", a.id, "update", after=a,
                    remark=f"批量熔接：芯{a.core_no} ↔ 芯{b.core_no}")
        await audit(db, user.id, "core", b.id, "update", after=b,
                    remark=f"批量熔接：芯{b.core_no} ↔ 芯{a.core_no}")
        succeeded.append({"a": pr.core_a_id, "b": pr.core_b_id,
                          "a_no": a.core_no, "b_no": b.core_no})

    await db.commit()
    return {
        "succeeded": succeeded,
        "failed": failed,
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
    }
