"""devices + ports + 设备面板设计器（自定义模板）。

设备创建支持三种来源：
1. 内置模板（device_templates.TEMPLATES）
2. 自定义模板（CustomDeviceTemplate，由设计器绘制）
3. 即时端口组（body.port_groups）
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.device_templates import (CATEGORIES, DEFAULT_U_HEIGHT, TEMPLATE_BY_KEY,
                                        TEMPLATES, build_ports, build_ports_from_layout,
                                        u_height_of)
from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import CustomDeviceTemplate, Device, Port, Rack
from app.services.audit import audit, to_dict
from app.services.occupancy import find_u_conflict, span
from app.services.perms import assert_device, assert_port, assert_rack
from app.services.port_types import check_compatibility, port_types_payload

router = APIRouter(tags=["devices"])

# 未指定模板时按 device_type 回退到默认模板（保持旧调用方式可用）
DEFAULT_TEMPLATE_BY_TYPE = {
    "sw": "sw-24ge-4sfp",
    "olt": "olt-16pon",
    "oadm": "oadm-8ch",
    "amp": "amp-edfa-2",
    "tx": "otp-2x10g",
    "rx": "otp-2x10g",
    "media_conv": "mc-1",
}


class PortGroupIn(BaseModel):
    name: str
    prefix: str = ""
    count: int = 0
    type: str = "LC/UPC"


class DeviceIn(BaseModel):
    rack_id: int
    name: str
    model: str = ""
    device_type: str = "sw"
    category: str = ""
    template_key: str = ""
    port_groups: list[PortGroupIn] | None = None
    svg_key: str = ""
    u_position: int = 1
    u_height: int | None = None      # 占用 U 数；留空则按模板/类别默认
    port_layout: str = "horizontal"  # horizontal | vertical
    mgmt_ip: str | None = None
    remark: str = ""


class DevicePatchIn(BaseModel):
    name: str | None = None
    model: str | None = None
    u_position: int | None = None
    u_height: int | None = None
    port_layout: str | None = None
    mgmt_ip: str | None = None
    remark: str | None = None


class PortIn(BaseModel):
    port_no: str
    port_type: str = "LC/UPC"
    group_name: str = ""
    group_seq: int = 0
    status: str = "free"
    label: str = ""
    remark: str = ""


# ---------------- 模板库 ----------------
@router.get("/device-templates")
async def list_device_templates(db: AsyncSession = Depends(get_db)):
    """内置模板 + 用户自定义模板 + 端口类型字典。"""
    builtin = []
    for t in TEMPLATES:
        item = dict(t)
        item["u_height"] = u_height_of(t["key"], t["category"])
        item["builtin"] = True
        builtin.append(item)

    customs = (await db.execute(select(CustomDeviceTemplate).order_by(CustomDeviceTemplate.id))).scalars().all()
    custom_items = [{
        "key": c.key,
        "name": c.name,
        "category": c.category,
        "device_type": c.device_type,
        "layout": "horizontal",
        "width": c.width,
        "height": c.height,
        "u_height": c.u_height,
        "groups": [],
        "layout_json": c.layout_json,
        "builtin": False,
        "id": c.id,
        "remark": c.remark,
    } for c in customs]

    return {
        "categories": CATEGORIES,
        "templates": builtin + custom_items,
        "port_types": port_types_payload(),
        "default_u_height": DEFAULT_U_HEIGHT,
    }


# ---------------- 自定义模板（设计器） ----------------
class LayoutPort(BaseModel):
    no: str
    type: str = "LC/UPC"
    group: str = ""
    group_seq: int = 0
    x: float = 0
    y: float = 0


class CustomTemplateIn(BaseModel):
    name: str
    category: str = "custom"
    device_type: str = "custom"
    width: int = 480
    height: int = 44
    u_height: int = 1
    remark: str = ""
    ports: list[LayoutPort] = []


@router.post("/custom-templates")
async def create_custom_template(body: CustomTemplateIn, db: AsyncSession = Depends(get_db),
                                 user=Depends(get_current_user)):
    if not body.ports:
        raise HTTPException(400, "至少需要一个端口")
    key = f"ct-{user.id}-{int(__import__('time').time() * 1000)}"
    layout = {
        "width": body.width,
        "height": body.height,
        "ports": [p.model_dump() for p in body.ports],
    }
    tpl = CustomDeviceTemplate(
        key=key, name=body.name, category=body.category, device_type=body.device_type,
        width=body.width, height=body.height, u_height=body.u_height,
        layout_json=layout, remark=body.remark, created_by=user.id,
    )
    db.add(tpl)
    await db.flush()
    await audit(db, user.id, "custom_template", tpl.id, "create", after=tpl, remark="设计器创建模板")
    await db.commit()
    await db.refresh(tpl)
    return {"id": tpl.id, "key": tpl.key, "name": tpl.name}


@router.put("/custom-templates/{tpl_id}")
async def update_custom_template(tpl_id: int, body: CustomTemplateIn, db: AsyncSession = Depends(get_db),
                                 user=Depends(get_current_user)):
    tpl = (await db.execute(select(CustomDeviceTemplate).where(
        CustomDeviceTemplate.id == tpl_id))).scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "模板不存在")
    before = to_dict(tpl)
    tpl.name = body.name
    tpl.category = body.category
    tpl.device_type = body.device_type
    tpl.width = body.width
    tpl.height = body.height
    tpl.u_height = body.u_height
    tpl.remark = body.remark
    tpl.layout_json = {
        "width": body.width, "height": body.height,
        "ports": [p.model_dump() for p in body.ports],
    }
    await audit(db, user.id, "custom_template", tpl.id, "update", before=before, after=to_dict(tpl))
    await db.commit()
    return to_dict(tpl)


@router.delete("/custom-templates/{tpl_id}")
async def delete_custom_template(tpl_id: int, db: AsyncSession = Depends(get_db),
                                 user=Depends(get_current_user)):
    tpl = (await db.execute(select(CustomDeviceTemplate).where(
        CustomDeviceTemplate.id == tpl_id))).scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "模板不存在")
    await audit(db, user.id, "custom_template", tpl.id, "delete", before=to_dict(tpl))
    await db.delete(tpl)
    await db.commit()
    return {"ok": True}


# ---------------- 设备 ----------------
@router.get("/devices")
async def list_devices(rack_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Device)
    if rack_id:
        q = q.where(Device.rack_id == rack_id)
    return [to_dict(d) for d in (await db.execute(q)).scalars()]


@router.post("/devices")
async def create_device(body: DeviceIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if not (await db.execute(select(Rack).where(Rack.id == body.rack_id))).scalar_one_or_none():
        raise HTTPException(404, "机柜不存在")
    await assert_rack(db, user, body.rack_id)

    # 三种端口来源
    tpl_key = body.template_key or (
        "" if body.port_groups else DEFAULT_TEMPLATE_BY_TYPE.get(body.device_type, ""))
    tpl = TEMPLATE_BY_KEY.get(tpl_key) if tpl_key else None
    custom = None
    if not tpl and tpl_key:
        custom = (await db.execute(select(CustomDeviceTemplate).where(
            CustomDeviceTemplate.key == tpl_key))).scalar_one_or_none()

    groups: list[dict] = []
    category = body.category
    device_type = body.device_type
    svg_key = body.svg_key
    panel_width = 480
    layout = body.port_layout or "horizontal"

    if tpl:
        groups = list(tpl["groups"])
        category = category or tpl["category"]
        device_type = tpl["device_type"]
        panel_width = int(tpl.get("width") or 480)
        layout = body.port_layout if body.port_layout != "horizontal" else tpl.get("layout", "horizontal")
    elif custom:
        category = category or custom.category
        device_type = custom.device_type or device_type
        panel_width = custom.width
        groups = []  # 端口从 layout_json 取
    elif body.port_groups:
        groups = [g.model_dump() for g in body.port_groups]

    if not svg_key:
        svg_key = f"{category or device_type}-generic"

    uh = body.u_height if body.u_height else (
        custom.u_height if custom else u_height_of(tpl_key, category))

    # U 位冲突校验
    conflict = await find_u_conflict(db, body.rack_id, body.u_position, uh)
    if conflict:
        c0, c1 = span(conflict.u_position, conflict.u_height or 1)
        raise HTTPException(
            409,
            f"U 位冲突：本设备将占用 U{body.u_position}–U{body.u_position + uh - 1}，"
            f"与「{conflict.name}」(U{c0}–U{c1}) 重叠",
        )

    dev = Device(
        rack_id=body.rack_id, name=body.name, model=body.model,
        device_type=device_type, category=category or device_type,
        template_key=tpl_key, svg_key=svg_key,
        u_position=body.u_position, u_height=uh,
        port_layout=layout, panel_width=panel_width,
        mgmt_ip=body.mgmt_ip, remark=body.remark,
    )
    db.add(dev)
    await db.flush()

    if custom and custom.layout_json:
        ports_data = build_ports_from_layout(custom.layout_json)
    else:
        ports_data = build_ports(groups)
    for p in ports_data:
        db.add(Port(owner_type="device", owner_id=dev.id, **p))

    await audit(db, user.id, "device", dev.id, "create", after=dev)
    await db.commit()
    await db.refresh(dev)
    return to_dict(dev)


@router.put("/devices/{device_id}")
async def update_device(device_id: int, body: DevicePatchIn, db: AsyncSession = Depends(get_db),
                        user=Depends(get_current_user)):
    dev = (await db.execute(select(Device).where(Device.id == device_id))).scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "设备不存在")
    await assert_device(db, user, device_id)
    before = Device(**to_dict(dev))
    patch = body.model_dump(exclude_none=True)

    if "u_position" in patch or "u_height" in patch:
        new_pos = patch.get("u_position", dev.u_position)
        new_h = patch.get("u_height", dev.u_height or 1)
        conflict = await find_u_conflict(db, dev.rack_id, new_pos, new_h, exclude_device_id=dev.id)
        if conflict:
            c0, c1 = span(conflict.u_position, conflict.u_height or 1)
            raise HTTPException(
                409,
                f"U 位冲突：将占用 U{new_pos}–U{new_pos + new_h - 1}，"
                f"与「{conflict.name}」(U{c0}–U{c1}) 重叠",
            )

    for k, v in patch.items():
        setattr(dev, k, v)
    await audit(db, user.id, "device", dev.id, "update", before=before, after=dev)
    await db.commit()
    return to_dict(dev)


@router.delete("/devices/{device_id}")
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    dev = (await db.execute(select(Device).where(Device.id == device_id))).scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "设备不存在")
    await assert_device(db, user, device_id)
    ports = (await db.execute(
        select(Port).where(Port.owner_type == "device", Port.owner_id == device_id))).scalars().all()
    used = [p for p in ports if p.status == "used"]
    if used:
        raise HTTPException(409, f"设备有 {len(used)} 个在用端口（有连接），请先解除连接")
    for p in ports:
        await db.delete(p)
    await audit(db, user.id, "device", dev.id, "delete", before=dev)
    await db.delete(dev)
    await db.commit()
    return {"ok": True}


# ---------------- 端口 ----------------
@router.get("/ports")
async def list_ports(owner_type: str | None = None, owner_id: int | None = None,
                     db: AsyncSession = Depends(get_db)):
    q = select(Port).order_by(Port.id)
    if owner_type:
        q = q.where(Port.owner_type == owner_type)
    if owner_id:
        q = q.where(Port.owner_id == owner_id)
    return [to_dict(p) for p in (await db.execute(q)).scalars()]


@router.post("/devices/{device_id}/ports")
async def add_device_port(device_id: int, body: PortIn, db: AsyncSession = Depends(get_db),
                          user=Depends(get_current_user)):
    dev = (await db.execute(select(Device).where(Device.id == device_id))).scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "设备不存在")
    await assert_device(db, user, device_id)
    exists = (await db.execute(select(Port).where(
        Port.owner_type == "device", Port.owner_id == device_id, Port.port_no == body.port_no))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"端口 {body.port_no} 已存在")
    port = Port(owner_type="device", owner_id=device_id, **body.model_dump())
    db.add(port)
    await db.flush()
    await audit(db, user.id, "port", port.id, "create", after=port)
    await db.commit()
    await db.refresh(port)
    return to_dict(port)


@router.put("/ports/{port_id}")
async def update_port(port_id: int, body: PortIn, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)):
    port = (await db.execute(select(Port).where(Port.id == port_id))).scalar_one_or_none()
    if not port:
        raise HTTPException(404, "端口不存在")
    await assert_port(db, user, port_id)
    before = Port(**to_dict(port))
    for k, v in body.model_dump().items():
        setattr(port, k, v)
    await audit(db, user.id, "port", port.id, "update", before=before, after=port)
    await db.commit()
    return to_dict(port)


@router.delete("/ports/{port_id}")
async def delete_port(port_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    port = (await db.execute(select(Port).where(Port.id == port_id))).scalar_one_or_none()
    if not port:
        raise HTTPException(404, "端口不存在")
    await assert_port(db, user, port_id)
    if port.status == "used":
        raise HTTPException(409, "端口在用（有连接），请先解除连接")
    await audit(db, user.id, "port", port.id, "delete", before=port)
    await db.delete(port)
    await db.commit()
    return {"ok": True}


# ---------------- 兼容性预检 ----------------
@router.get("/ports/compat")
async def check_port_compat(a: int, b: int, db: AsyncSession = Depends(get_db)):
    """建跳纤前的兼容性预检，返回 ok / warn / block 与提示文案。"""
    pa = (await db.execute(select(Port).where(Port.id == a))).scalar_one_or_none()
    pb = (await db.execute(select(Port).where(Port.id == b))).scalar_one_or_none()
    if not pa or not pb:
        raise HTTPException(404, "端口不存在")
    level, msg = check_compatibility(pa.port_type, pb.port_type)
    return {"level": level, "message": msg,
            "a_type": pa.port_type, "b_type": pb.port_type}


# ---------------- 批量状态（供外部管理平台推送） ----------------
class BatchStatusItem(BaseModel):
    port_id: int
    status: str                       # free / used / reserved / fault
    remark: str | None = None


class BatchStatusIn(BaseModel):
    items: list[BatchStatusItem]
    source: str = "manual"            # 来源标记，写入变更备注


@router.post("/ports/batch-status")
async def batch_set_port_status(body: BatchStatusIn, db: AsyncSession = Depends(get_db),
                                user=Depends(get_current_user)):
    """批量更新端口状态（供外部在线管理平台实时推送）。"""
    valid = {"free", "used", "reserved", "fault"}
    updated, failed = [], []

    for item in body.items:
        if item.status not in valid:
            failed.append({"port_id": item.port_id, "reason": f"非法状态 {item.status}"})
            continue
        port = (await db.execute(select(Port).where(Port.id == item.port_id))).scalar_one_or_none()
        if not port:
            failed.append({"port_id": item.port_id, "reason": "端口不存在"})
            continue
        try:
            await assert_port(db, user, item.port_id)
        except HTTPException as e:
            failed.append({"port_id": item.port_id, "reason": e.detail})
            continue
        if port.status == "used" and item.status == "free":
            failed.append({"port_id": item.port_id, "reason": "端口有在用连接，不能直接置为空闲"})
            continue
        before_status = port.status
        if before_status == item.status and (item.remark is None or item.remark == port.remark):
            continue
        old = Port(**to_dict(port))
        port.status = item.status
        if item.remark is not None:
            port.remark = item.remark
        await audit(db, user.id, "port", port.id, "update", before=old, after=port,
                    remark=f"批量状态更新（{body.source}）")
        updated.append({"port_id": item.port_id, "from": before_status, "to": item.status})

    await db.commit()
    return {"updated": updated, "failed": failed,
            "updated_count": len(updated), "failed_count": len(failed)}
