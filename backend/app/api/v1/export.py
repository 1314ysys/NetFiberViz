"""台账导出：多 sheet xlsx（设备/端口/跳纤/孔位）+ 变更记录导出。"""
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models import Cable, ChangeLog, Device, Interconnect, OdfSlot, PatchCord, Port, Rack, Room

import openpyxl

router = APIRouter(prefix="/export", tags=["export"])


def _sheet(wb, title, headers, rows):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for r in rows:
        ws.append(r)


@router.get("/inventory")
async def export_inventory(db: AsyncSession = Depends(get_db)):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    rooms = {r.id: r.name for r in (await db.execute(select(Room))).scalars()}
    racks = {r.id: r for r in (await db.execute(select(Rack))).scalars()}
    devices = (await db.execute(select(Device))).scalars().all()
    _sheet(wb, "设备台账", ["ID", "机房", "机柜", "名称", "型号", "类型", "U位", "管理IP"],
           [[d.id, rooms.get(racks[d.rack_id].room_id) if d.rack_id in racks else "",
             racks[d.rack_id].name if d.rack_id in racks else "", d.name, d.model,
             d.device_type, d.u_position, d.mgmt_ip or ""] for d in devices])

    ports = (await db.execute(select(Port))).scalars().all()
    dev_names = {d.id: d.name for d in devices}
    slot_rows = []
    for s in (await db.execute(select(OdfSlot))).scalars():
        p = next((p for p in ports if p.id == s.port_id), None)
        slot_rows.append([s.id, s.row_label + str(s.col_no), p.status if p else ""])
    _sheet(wb, "ODF孔位", ["slot_id", "编址", "状态"], slot_rows)
    _sheet(wb, "端口台账", ["ID", "归属", "端口号", "类型", "状态", "标签"],
           [[p.id, dev_names.get(p.owner_id, "") if p.owner_type == "device" else "ODF",
             p.port_no, p.port_type, p.status, p.label] for p in ports])

    _sheet(wb, "在用跳纤", ["ID", "A端端口ID", "B端端口ID", "型号", "长度(m)", "备注"],
           [[c.id, c.port_a_id, c.port_b_id, c.cord_type, c.length_m, c.remark]
            for c in (await db.execute(select(PatchCord).where(PatchCord.status == "active"))).scalars()])
    _sheet(wb, "盘间连接", ["ID", "A孔位ID", "B孔位ID", "类型", "备注"],
           [[i.id, i.slot_a_id, i.slot_b_id, i.kind, i.remark]
            for i in (await db.execute(select(Interconnect))).scalars()])
    _sheet(wb, "光缆", ["ID", "名称", "芯数", "型号", "来向"],
           [[c.id, c.name, c.core_count, c.cable_type, c.direction_from]
            for c in (await db.execute(select(Cable))).scalars()])

    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=inventory.xlsx"})


@router.get("/changes")
async def export_changes(db: AsyncSession = Depends(get_db)):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    logs = (await db.execute(select(ChangeLog).order_by(ChangeLog.ts))).scalars().all()
    _sheet(wb, "变更记录", ["ID", "用户ID", "时间", "对象", "对象ID", "动作", "变更前", "变更后", "备注"],
           [[c.id, c.user_id, c.ts.strftime("%Y-%m-%d %H:%M:%S"), c.entity_type, c.entity_id,
             c.action, str(c.before_json or ""), str(c.after_json or ""), c.remark] for c in logs])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=changes.xlsx"})
