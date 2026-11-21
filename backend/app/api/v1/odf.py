"""ODF：配线柜 / 单元柜 / 盘 / 孔位。

组合模型：
- 盘是最小单元（默认 1 行 × 12 孔），可独立存在并自由拖拽（归属"未分组"容器）
- 多选盘 → 组合为单元柜（自动垂直对齐吸附、按单元柜名重新编址）
- 单元柜可解散，盘回到未分组
- 也可先建单元柜（指定盘数）或先建配线柜（指定单元柜数）
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import OdfCabinet, OdfSlot, OdfTray, OdfUnit, Port, Room
from app.services.audit import audit, to_dict
from app.services.perms import assert_cabinet, assert_room, assert_tray, assert_unit

router = APIRouter(prefix="/odf", tags=["odf"])

ROW_H = 56  # 盘在单元柜内的垂直间距（画布单位）


def slot_label(unit_name: str, row_label: str, col_no: int) -> str:
    return f"{unit_name}{row_label}{col_no}" if row_label else f"{unit_name}{col_no}"


# ---------------- 配线柜 ----------------
class CabinetIn(BaseModel):
    room_id: int
    name: str
    code: str
    pos_x: float = 0
    pos_y: float = 0
    group_id: str | None = None


class CabinetPatchIn(BaseModel):
    name: str | None = None
    code: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None


@router.get("/cabinets")
async def list_cabinets(room_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(OdfCabinet)
    if room_id:
        q = q.where(OdfCabinet.room_id == room_id)
    return [to_dict(c) for c in (await db.execute(q)).scalars()]


@router.post("/cabinets")
async def create_cabinet(body: CabinetIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if not (await db.execute(select(Room).where(Room.id == body.room_id))).scalar_one_or_none():
        raise HTTPException(404, "机房不存在")
    await assert_room(db, user, body.room_id)
    cab = OdfCabinet(**body.model_dump())
    db.add(cab)
    await db.flush()
    await audit(db, user.id, "odf_cabinet", cab.id, "create", after=cab)
    await db.commit()
    await db.refresh(cab)
    return to_dict(cab)


@router.put("/cabinets/{cabinet_id}")
async def update_cabinet(cabinet_id: int, body: CabinetPatchIn, db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)):
    cab = (await db.execute(select(OdfCabinet).where(OdfCabinet.id == cabinet_id))).scalar_one_or_none()
    if not cab:
        raise HTTPException(404, "配线柜不存在")
    await assert_cabinet(db, user, cabinet_id)
    before = OdfCabinet(**to_dict(cab))
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(cab, k, v)
    await audit(db, user.id, "odf_cabinet", cab.id, "update", before=before, after=cab)
    await db.commit()
    return to_dict(cab)


@router.delete("/cabinets/{cabinet_id}")
async def delete_cabinet(cabinet_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    cab = (await db.execute(select(OdfCabinet).where(OdfCabinet.id == cabinet_id))).scalar_one_or_none()
    if not cab:
        raise HTTPException(404, "配线柜不存在")
    await assert_cabinet(db, user, cabinet_id)
    units = (await db.execute(select(OdfUnit).where(OdfUnit.cabinet_id == cabinet_id))).scalars().all()
    tray_ids: list[int] = []
    for u in units:
        for t in (await db.execute(select(OdfTray).where(OdfTray.unit_id == u.id))).scalars():
            tray_ids.append(t.id)
    if tray_ids:
        used = (await db.execute(select(Port).where(
            Port.owner_type == "odf_slot", Port.status == "used"))).scalars().all()
        if used:
            raise HTTPException(409, "配线柜内存在在用孔位，禁止删除")
        for tid in tray_ids:
            for s in (await db.execute(select(OdfSlot).where(OdfSlot.tray_id == tid))).scalars():
                port = (await db.execute(select(Port).where(Port.id == s.port_id))).scalar_one_or_none()
                if port:
                    await db.delete(port)
                await db.delete(s)
            tray = (await db.execute(select(OdfTray).where(OdfTray.id == tid))).scalar_one_or_none()
            if tray:
                await db.delete(tray)
    for u in units:
        await db.delete(u)
    await audit(db, user.id, "odf_cabinet", cab.id, "delete", before=cab)
    await db.delete(cab)
    await db.commit()
    return {"ok": True}


# ---------------- 单元柜 ----------------
async def get_or_create_pending_unit(db: AsyncSession, cabinet_id: int) -> OdfUnit:
    """未分组容器：承载尚未组合的盘。"""
    unit = (await db.execute(select(OdfUnit).where(
        OdfUnit.cabinet_id == cabinet_id, OdfUnit.is_pending.is_(True)))).scalar_one_or_none()
    if not unit:
        unit = OdfUnit(cabinet_id=cabinet_id, name="未分组", seq=9999, is_pending=True)
        db.add(unit)
        await db.flush()
    return unit


class UnitIn(BaseModel):
    cabinet_id: int
    name: str
    seq: int = 1
    pos_x: float = 0
    pos_y: float = 0
    tray_count: int = 0          # 创建时即生成 N 个盘
    slots_per_row: int = 12
    rows: int = 1


class UnitPatchIn(BaseModel):
    name: str | None = None
    seq: int | None = None
    pos_x: float | None = None
    pos_y: float | None = None


@router.get("/units")
async def list_units(cabinet_id: int | None = None, include_pending: bool = False,
                     db: AsyncSession = Depends(get_db)):
    q = select(OdfUnit)
    if cabinet_id:
        q = q.where(OdfUnit.cabinet_id == cabinet_id)
    if not include_pending:
        q = q.where(OdfUnit.is_pending.is_(False))
    return [to_dict(u) for u in (await db.execute(q.order_by(OdfUnit.seq))).scalars()]


@router.post("/units")
async def create_unit(body: UnitIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if not (await db.execute(select(OdfCabinet).where(OdfCabinet.id == body.cabinet_id))).scalar_one_or_none():
        raise HTTPException(404, "ODF 配线柜不存在")
    await assert_cabinet(db, user, body.cabinet_id)
    dup = (await db.execute(select(OdfUnit).where(
        OdfUnit.cabinet_id == body.cabinet_id, OdfUnit.name == body.name))).scalar_one_or_none()
    if dup:
        raise HTTPException(409, f"单元柜 {body.name} 已存在")
    unit = OdfUnit(cabinet_id=body.cabinet_id, name=body.name, seq=body.seq,
                   pos_x=body.pos_x, pos_y=body.pos_y)
    db.add(unit)
    await db.flush()

    # 先建单元柜 → 直接生成 N 个盘
    for i in range(body.tray_count):
        await _create_tray(db, unit, name=str(i + 1), seq=i + 1,
                           slots_per_row=body.slots_per_row, rows=body.rows,
                           pos_x=body.pos_x, pos_y=body.pos_y + i * ROW_H)

    await audit(db, user.id, "odf_unit", unit.id, "create", after=unit)
    await db.commit()
    await db.refresh(unit)
    return to_dict(unit)


@router.get("/units/{unit_id}")
async def get_unit(unit_id: int, db: AsyncSession = Depends(get_db)):
    unit = (await db.execute(select(OdfUnit).where(OdfUnit.id == unit_id))).scalar_one_or_none()
    if not unit:
        raise HTTPException(404, "单元柜不存在")
    return to_dict(unit)


@router.put("/units/{unit_id}")
async def update_unit(unit_id: int, body: UnitPatchIn, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)):
    unit = (await db.execute(select(OdfUnit).where(OdfUnit.id == unit_id))).scalar_one_or_none()
    if not unit:
        raise HTTPException(404, "单元柜不存在")
    await assert_unit(db, user, unit_id)
    before = OdfUnit(**to_dict(unit))
    rename = body.name is not None and body.name != unit.name
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(unit, k, v)
    if rename:
        # 改名后重新编址该单元下所有盘
        for t in (await db.execute(select(OdfTray).where(OdfTray.unit_id == unit.id))).scalars():
            await _relabel_tray(db, t, unit.name)
    await audit(db, user.id, "odf_unit", unit.id, "update", before=before, after=unit)
    await db.commit()
    return to_dict(unit)


@router.delete("/units/{unit_id}")
async def delete_unit(unit_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """删除单元柜：内部盘回落到未分组（不删除盘）。"""
    unit = (await db.execute(select(OdfUnit).where(OdfUnit.id == unit_id))).scalar_one_or_none()
    if not unit:
        raise HTTPException(404, "单元柜不存在")
    if unit.is_pending:
        raise HTTPException(400, "未分组容器不可删除")
    await assert_unit(db, user, unit_id)
    pending = await get_or_create_pending_unit(db, unit.cabinet_id)
    for t in (await db.execute(select(OdfTray).where(OdfTray.unit_id == unit.id))).scalars():
        t.unit_id = pending.id
        await _relabel_tray(db, t, f"T{t.id}")
    await audit(db, user.id, "odf_unit", unit.id, "delete", before=unit)
    await db.delete(unit)
    await db.commit()
    return {"ok": True}


@router.post("/units/{unit_id}/ungroup")
async def ungroup_unit(unit_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """解散单元柜：盘保留当前位置回到未分组。"""
    return await delete_unit(unit_id, db, user)


# ---------------- 盘 ----------------
async def _relabel_tray(db: AsyncSession, tray: OdfTray, prefix: str) -> None:
    for s in (await db.execute(select(OdfSlot).where(OdfSlot.tray_id == tray.id))).scalars():
        port = (await db.execute(select(Port).where(Port.id == s.port_id))).scalar_one_or_none()
        if port:
            port.port_no = slot_label(prefix, s.row_label, s.col_no)


async def _create_tray(db: AsyncSession, unit: OdfUnit, name: str, seq: int,
                       slots_per_row: int, rows: int, pos_x: float, pos_y: float) -> OdfTray:
    tray = OdfTray(unit_id=unit.id, name=name, slots_per_row=slots_per_row, rows=rows,
                   seq=seq, pos_x=pos_x, pos_y=pos_y)
    db.add(tray)
    await db.flush()
    prefix = f"T{tray.id}" if unit.is_pending else unit.name
    for r in range(1, rows + 1):
        row_label = chr(ord("A") + r - 1) if rows == 2 else ""
        for c in range(1, slots_per_row + 1):
            port = Port(owner_type="odf_slot", owner_id=0,
                        port_no=slot_label(prefix, row_label, c), port_type="LC/UPC")
            db.add(port)
            await db.flush()
            slot = OdfSlot(tray_id=tray.id, row_label=row_label, col_no=c, port_id=port.id)
            db.add(slot)
            await db.flush()
            port.owner_id = slot.id
    return tray


class TrayIn(BaseModel):
    cabinet_id: int | None = None
    unit_id: int | None = None
    name: str
    slots_per_row: int = 12
    rows: int = 1
    seq: int = 1
    pos_x: float = 0
    pos_y: float = 0


class TrayPatchIn(BaseModel):
    name: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    unit_id: int | None = None


class TrayGroupIn(BaseModel):
    cabinet_id: int
    tray_ids: list[int]
    name: str
    pos_x: float = 0
    pos_y: float = 0


@router.get("/trays")
async def list_trays(unit_id: int | None = None, cabinet_id: int | None = None,
                     db: AsyncSession = Depends(get_db)):
    q = select(OdfTray)
    if unit_id:
        q = q.where(OdfTray.unit_id == unit_id)
    elif cabinet_id:
        unit_ids = [u.id for u in (await db.execute(
            select(OdfUnit).where(OdfUnit.cabinet_id == cabinet_id))).scalars()]
        if not unit_ids:
            return []
        q = q.where(OdfTray.unit_id.in_(unit_ids))
    trays = (await db.execute(q.order_by(OdfTray.seq))).scalars().all()
    out = []
    for t in trays:
        d = to_dict(t)
        slot_count = len((await db.execute(select(OdfSlot).where(OdfSlot.tray_id == t.id))).scalars().all())
        used = 0
        for s in (await db.execute(select(OdfSlot).where(OdfSlot.tray_id == t.id))).scalars():
            p = (await db.execute(select(Port).where(Port.id == s.port_id))).scalar_one_or_none()
            if p and p.status == "used":
                used += 1
        d["slot_count"] = slot_count
        d["used_count"] = used
        out.append(d)
    return out


@router.post("/trays")
async def create_tray(body: TrayIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if body.rows not in (1, 2) or body.slots_per_row not in (6, 12):
        raise HTTPException(400, "盘规格仅支持 1×12 或 2×6")

    if body.unit_id:
        unit = (await db.execute(select(OdfUnit).where(OdfUnit.id == body.unit_id))).scalar_one_or_none()
        if not unit:
            raise HTTPException(404, "单元柜不存在")
        await assert_unit(db, user, body.unit_id)
    elif body.cabinet_id:
        if not (await db.execute(select(OdfCabinet).where(OdfCabinet.id == body.cabinet_id))).scalar_one_or_none():
            raise HTTPException(404, "ODF 配线柜不存在")
        await assert_cabinet(db, user, body.cabinet_id)
        unit = await get_or_create_pending_unit(db, body.cabinet_id)
    else:
        raise HTTPException(400, "需提供 unit_id 或 cabinet_id")

    tray = await _create_tray(db, unit, body.name, body.seq, body.slots_per_row, body.rows,
                              body.pos_x, body.pos_y)
    await audit(db, user.id, "odf_tray", tray.id, "create", after=tray)
    await db.commit()
    await db.refresh(tray)
    return to_dict(tray)


@router.put("/trays/{tray_id}")
async def update_tray(tray_id: int, body: TrayPatchIn, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)):
    tray = (await db.execute(select(OdfTray).where(OdfTray.id == tray_id))).scalar_one_or_none()
    if not tray:
        raise HTTPException(404, "盘不存在")
    await assert_tray(db, user, tray_id)
    before = OdfTray(**to_dict(tray))
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(tray, k, v)
    if body.name is not None:
        unit = (await db.execute(select(OdfUnit).where(OdfUnit.id == tray.unit_id))).scalar_one()
        await _relabel_tray(db, tray, f"T{tray.id}" if unit.is_pending else unit.name)
    await audit(db, user.id, "odf_tray", tray.id, "update", before=before, after=tray)
    await db.commit()
    return to_dict(tray)


@router.delete("/trays/{tray_id}")
async def delete_tray(tray_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    tray = (await db.execute(select(OdfTray).where(OdfTray.id == tray_id))).scalar_one_or_none()
    if not tray:
        raise HTTPException(404, "盘不存在")
    await assert_tray(db, user, tray_id)
    slots = (await db.execute(select(OdfSlot).where(OdfSlot.tray_id == tray_id))).scalars().all()
    for s in slots:
        port = (await db.execute(select(Port).where(Port.id == s.port_id))).scalar_one_or_none()
        if port and port.status == "used":
            raise HTTPException(409, f"孔位 {port.port_no} 在用，请先解除连接")
    for s in slots:
        port = (await db.execute(select(Port).where(Port.id == s.port_id))).scalar_one_or_none()
        if port:
            await db.delete(port)
        await db.delete(s)
    await audit(db, user.id, "odf_tray", tray.id, "delete", before=tray)
    await db.delete(tray)
    await db.commit()
    return {"ok": True}


@router.get("/trays/{tray_id}")
async def get_tray(tray_id: int, db: AsyncSession = Depends(get_db)):
    tray = (await db.execute(select(OdfTray).where(OdfTray.id == tray_id))).scalar_one_or_none()
    if not tray:
        raise HTTPException(404, "盘不存在")
    unit = (await db.execute(select(OdfUnit).where(OdfUnit.id == tray.unit_id))).scalar_one_or_none()
    d = to_dict(tray)
    d["cabinet_id"] = unit.cabinet_id if unit else None
    d["unit_name"] = unit.name if unit else ""
    return d


@router.post("/trays/group")
async def group_trays(body: TrayGroupIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """多选盘 → 组合为单元柜：自动垂直对齐吸附 + 按单元柜名重新编址。"""
    if len(body.tray_ids) < 1:
        raise HTTPException(400, "至少选择一个盘")
    if not (await db.execute(select(OdfCabinet).where(OdfCabinet.id == body.cabinet_id))).scalar_one_or_none():
        raise HTTPException(404, "ODF 配线柜不存在")
    await assert_cabinet(db, user, body.cabinet_id)
    dup = (await db.execute(select(OdfUnit).where(
        OdfUnit.cabinet_id == body.cabinet_id, OdfUnit.name == body.name))).scalar_one_or_none()
    if dup:
        raise HTTPException(409, f"单元柜 {body.name} 已存在")

    trays: list[OdfTray] = []
    for tid in body.tray_ids:
        t = (await db.execute(select(OdfTray).where(OdfTray.id == tid))).scalar_one_or_none()
        if not t:
            raise HTTPException(404, f"盘 {tid} 不存在")
        trays.append(t)

    unit = OdfUnit(cabinet_id=body.cabinet_id, name=body.name, seq=1,
                   pos_x=body.pos_x, pos_y=body.pos_y)
    db.add(unit)
    await db.flush()

    trays.sort(key=lambda t: (t.pos_y, t.id))
    for i, t in enumerate(trays):
        t.unit_id = unit.id
        t.pos_x = body.pos_x
        t.pos_y = body.pos_y + i * ROW_H
        await _relabel_tray(db, t, unit.name)

    await audit(db, user.id, "odf_unit", unit.id, "create", after=unit, remark="盘组合为单元柜")
    await db.commit()
    await db.refresh(unit)
    return {"unit": to_dict(unit), "trays": len(trays)}


@router.get("/cabinets/{cabinet_id}/layout")
async def cabinet_layout(cabinet_id: int, db: AsyncSession = Depends(get_db)):
    """配线柜内部布局：非未分组单元柜 + 全部盘（含坐标）。"""
    units = (await db.execute(select(OdfUnit).where(
        OdfUnit.cabinet_id == cabinet_id, OdfUnit.is_pending.is_(False)))).scalars().all()
    pending = (await db.execute(select(OdfUnit).where(
        OdfUnit.cabinet_id == cabinet_id, OdfUnit.is_pending.is_(True)))).scalar_one_or_none()
    trays = (await db.execute(select(OdfTray).where(
        OdfTray.unit_id.in_([u.id for u in units] + ([pending.id] if pending else []))))).scalars().all()
    return {
        "units": [to_dict(u) for u in units],
        "pending_unit_id": pending.id if pending else None,
        "trays": [to_dict(t) for t in trays],
    }


@router.get("/port-map")
async def port_map(room_id: int | None = None, db: AsyncSession = Depends(get_db)):
    """ODF 孔位端口 → 所属配线柜映射（供机房画布做机柜间连线聚合，避免前端 N+1 查询）。"""
    cabs = (await db.execute(select(OdfCabinet))).scalars().all()
    cab_by_id = {c.id: c for c in cabs}
    units = (await db.execute(select(OdfUnit))).scalars().all()
    unit_by_id = {u.id: u for u in units}
    trays = (await db.execute(select(OdfTray))).scalars().all()
    tray_by_id = {t.id: t for t in trays}
    slots = (await db.execute(select(OdfSlot))).scalars().all()
    ports = {p.id: p for p in (await db.execute(
        select(Port).where(Port.owner_type == "odf_slot"))).scalars()}

    out = []
    for s in slots:
        port = ports.get(s.port_id)
        if not port:
            continue
        tray = tray_by_id.get(s.tray_id)
        unit = unit_by_id.get(tray.unit_id) if tray else None
        cab = cab_by_id.get(unit.cabinet_id) if unit else None
        if not cab:
            continue
        if room_id and cab.room_id != room_id:
            continue
        out.append({
            "port_id": port.id,
            "port_no": port.port_no,
            "status": port.status,
            "cabinet_id": cab.id,
            "cabinet_name": cab.name,
            "unit_name": unit.name if unit else "",
            "tray_name": tray.name if tray else "",
        })
    return out


# ---------------- 孔位 ----------------
@router.get("/slots")
async def list_slots(tray_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(OdfSlot)
    if tray_id:
        q = q.where(OdfSlot.tray_id == tray_id)
    slots = (await db.execute(q.order_by(OdfSlot.row_label, OdfSlot.col_no))).scalars().all()
    out = []
    for s in slots:
        d = to_dict(s)
        port = (await db.execute(select(Port).where(Port.id == s.port_id))).scalar_one_or_none()
        d["port"] = to_dict(port) if port else None
        d["label"] = port.port_no if port else ""
        out.append(d)
    return out
