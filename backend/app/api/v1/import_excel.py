"""Excel 模板下载 + 两段式导入（逐行校验，错误行明细返回，不允许部分静默成功）。"""
import io

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.db import get_db
from app.models import Device, Port, Rack, Room
from app.services.audit import audit
from app.services.occupancy import find_u_conflict, span
from app.services.perms import assert_rack, assert_room, require_core

router = APIRouter(prefix="/import", tags=["import"])

TEMPLATE_HEADERS = {
    "机房": ["name", "code", "address"],
    "机柜": ["room_code", "name", "code", "u_count"],
    "设备": ["rack_code", "name", "model", "device_type", "u_position", "u_height", "mgmt_ip"],
}


@router.get("/template")
async def download_template():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet, headers in TEMPLATE_HEADERS.items():
        ws = wb.create_sheet(sheet)
        ws.append(headers)
        ws.append({"机房": ["示例机房", "CR-01", "A栋2楼"],
                   "机柜": ["CR-01", "01架", "R01", 42],
                   "设备": ["R01", "汇聚交换机-01", "S5730", "sw", 1, 1, "10.0.0.1"]}[sheet])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fiber_template.xlsx"})


@router.post("/excel")
async def import_excel(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                       user=Depends(get_current_user)):
    """两段式第一步：解析+逐行校验，返回错误明细与可导入计数（不落库）。"""
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, f"文件过大，上限 {settings.max_upload_bytes // (1024 * 1024)} MB")
    if not raw:
        raise HTTPException(400, "空文件")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
    except Exception:
        raise HTTPException(400, "无法解析 Excel 文件")
    errors: list[dict] = []
    plan: dict[str, list] = {"rooms": [], "racks": [], "devices": []}
    room_codes, rack_codes = set(), set()

    existing_rooms = {r.code for r in (await db.execute(select(Room))).scalars()}
    existing_racks = {r.code for r in (await db.execute(select(Rack))).scalars()}

    ws = wb["机房"] if "机房" in wb.sheetnames else None
    if ws:
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not any(row):
                continue
            if not row[0] or not row[1]:
                errors.append({"sheet": "机房", "row": i, "error": "name/code 必填"})
                continue
            if row[1] in existing_rooms or row[1] in room_codes:
                errors.append({"sheet": "机房", "row": i, "error": f"机房编码 {row[1]} 重复"})
                continue
            room_codes.add(row[1])
            plan["rooms"].append({"name": str(row[0]), "code": str(row[1]), "address": str(row[2] or "")})

    ws = wb["机柜"] if "机柜" in wb.sheetnames else None
    if ws:
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not any(row):
                continue
            if not row[1] or not row[2] or not row[0]:
                errors.append({"sheet": "机柜", "row": i, "error": "room_code/name/code 必填"})
                continue
            if row[0] not in room_codes and row[0] not in existing_rooms:
                errors.append({"sheet": "机柜", "row": i, "error": f"机房编码 {row[0]} 不存在"})
                continue
            if row[2] in existing_racks or row[2] in rack_codes:
                errors.append({"sheet": "机柜", "row": i, "error": f"机柜编码 {row[2]} 重复"})
                continue
            rack_codes.add(row[2])
            plan["racks"].append({"room_code": str(row[0]), "name": str(row[1]), "code": str(row[2]),
                                  "u_count": int(row[3] or 42)})

    ws = wb["设备"] if "设备" in wb.sheetnames else None
    if ws:
        valid_types = {"sw", "olt", "oadm", "amp", "tx", "rx", "media_conv", "custom"}
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not any(row):
                continue
            if not row[0] or not row[1]:
                errors.append({"sheet": "设备", "row": i, "error": "rack_code/name 必填"})
                continue
            if row[0] not in rack_codes and row[0] not in existing_racks:
                errors.append({"sheet": "设备", "row": i, "error": f"机柜编码 {row[0]} 不存在"})
                continue
            dtype = str(row[3] or "sw")
            if dtype not in valid_types:
                errors.append({"sheet": "设备", "row": i, "error": f"设备类型 {dtype} 非法"})
                continue
            plan["devices"].append({"rack_code": str(row[0]), "name": str(row[1]), "model": str(row[2] or ""),
                                    "device_type": dtype, "u_position": int(row[4] or 1),
                                    "u_height": int(row[5] or 1),
                                    "mgmt_ip": str(row[6]) if len(row) > 6 and row[6] else None})

    return {"errors": errors, "error_count": len(errors),
            "plan": plan, "valid": len(errors) == 0,
            "counts": {k: len(v) for k, v in plan.items()}}


class ApplyIn(BaseModel):
    plan: dict


@router.post("/excel/apply")
async def import_apply(body: ApplyIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    plan = body.plan
    # 导入会创建顶层机房，仅核心管理员可执行；机柜/设备落库时再校验目标机房
    if plan.get("rooms"):
        await require_core(user)
    rooms = {r.code: r.id for r in (await db.execute(select(Room))).scalars()}
    racks = {r.code: r.id for r in (await db.execute(select(Rack))).scalars()}
    created = {"rooms": 0, "racks": 0, "devices": 0}
    for item in plan.get("rooms", []):
        room = Room(**item)
        db.add(room); await db.flush()
        rooms[room.code] = room.id; created["rooms"] += 1
        await audit(db, user.id, "room", room.id, "create", after=room, remark="Excel导入")
    for item in plan.get("racks", []):
        d = dict(item); d["room_id"] = rooms[d.pop("room_code")]
        await assert_room(db, user, d["room_id"])
        rack = Rack(**d)
        db.add(rack); await db.flush()
        racks[rack.code] = rack.id; created["racks"] += 1
        await audit(db, user.id, "rack", rack.id, "create", after=rack, remark="Excel导入")
    for item in plan.get("devices", []):
        d = dict(item); d["rack_id"] = racks[d.pop("rack_code")]
        await assert_rack(db, user, d["rack_id"])
        # 批量导入同样要保证机柜内 U 位不重叠
        uh = int(d.get("u_height") or 1)
        u_pos = int(d.get("u_position") or 1)
        conflict = await find_u_conflict(db, d["rack_id"], u_pos, uh)
        if conflict:
            c0, c1 = span(conflict.u_position, conflict.u_height or 1)
            raise HTTPException(
                409,
                f"设备「{d.get('name')}」U 位冲突：占用 U{u_pos}–U{u_pos + uh - 1}，"
                f"与「{conflict.name}」(U{c0}–U{c1}) 重叠，导入已中止",
            )
        d["u_height"] = uh
        dev = Device(**d)
        db.add(dev); await db.flush()
        from app.api.v1.devices import PORT_TEMPLATES
        for port_no, port_type in PORT_TEMPLATES.get(dev.device_type, []):
            db.add(Port(owner_type="device", owner_id=dev.id, port_no=port_no, port_type=port_type))
        created["devices"] += 1
        await audit(db, user.id, "device", dev.id, "create", after=dev, remark="Excel导入")
    await db.commit()
    return {"created": created}
