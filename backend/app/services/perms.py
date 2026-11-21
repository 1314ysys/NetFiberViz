"""权限：角色 + 机房作用域（含子孙）。

- core_admin：全量读写
- site_admin：只读浏览全部；写操作仅限被授权机房及其所有子孙机房

所有写接口必须调用本模块的 assert_*，不依赖前端隐藏按钮。
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (Cable, Device, OdfCabinet, OdfSlot, OdfTray, OdfUnit,
                        Port, Rack, Room, User, UserRoom)


async def user_scope(db: AsyncSession, user: User) -> set[int] | None:
    """返回可写机房 id 集合；None 表示全量权限。"""
    if user.role == "core_admin":
        return None
    granted = [r.room_id for r in (await db.execute(
        select(UserRoom).where(UserRoom.user_id == user.id))).scalars()]
    if not granted:
        return set()

    rows = (await db.execute(select(Room.id, Room.parent_id))).all()
    children: dict[int, list[int]] = {}
    for rid, pid in rows:
        children.setdefault(pid, []).append(rid)

    out: set[int] = set()
    stack = list(granted)
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))

    # 只保留仍然存在的机房
    alive = {rid for rid, _ in rows}
    return out & alive


async def assert_room(db: AsyncSession, user: User, room_id: int | None) -> None:
    if room_id is None:
        raise HTTPException(403, "无法确定资源所属机房，拒绝写入")
    scope = await user_scope(db, user)
    if scope is None:
        return
    if room_id not in scope:
        raise HTTPException(403, "无该机房的写权限")


# ---------------- 资源 → 机房 ----------------
async def room_of_rack(db: AsyncSession, rack_id: int) -> int | None:
    r = (await db.execute(select(Rack.room_id).where(Rack.id == rack_id))).scalar_one_or_none()
    return r


async def room_of_device(db: AsyncSession, device_id: int) -> int | None:
    row = (await db.execute(
        select(Rack.room_id).join(Device, Device.rack_id == Rack.id)
        .where(Device.id == device_id))).scalar_one_or_none()
    return row


async def room_of_port(db: AsyncSession, port_id: int) -> int | None:
    p = (await db.execute(select(Port).where(Port.id == port_id))).scalar_one_or_none()
    if not p:
        return None
    if p.owner_type == "device":
        return await room_of_device(db, p.owner_id)
    return await room_of_slot(db, p.owner_id)


async def room_of_slot(db: AsyncSession, slot_id: int) -> int | None:
    row = (await db.execute(
        select(OdfCabinet.room_id)
        .join(OdfUnit, OdfUnit.cabinet_id == OdfCabinet.id)
        .join(OdfTray, OdfTray.unit_id == OdfUnit.id)
        .join(OdfSlot, OdfSlot.tray_id == OdfTray.id)
        .where(OdfSlot.id == slot_id))).scalar_one_or_none()
    return row


async def room_of_cabinet(db: AsyncSession, cabinet_id: int) -> int | None:
    return (await db.execute(
        select(OdfCabinet.room_id).where(OdfCabinet.id == cabinet_id))).scalar_one_or_none()


async def room_of_unit(db: AsyncSession, unit_id: int) -> int | None:
    return (await db.execute(
        select(OdfCabinet.room_id)
        .join(OdfUnit, OdfUnit.cabinet_id == OdfCabinet.id)
        .where(OdfUnit.id == unit_id))).scalar_one_or_none()


async def room_of_tray(db: AsyncSession, tray_id: int) -> int | None:
    return (await db.execute(
        select(OdfCabinet.room_id)
        .join(OdfUnit, OdfUnit.cabinet_id == OdfCabinet.id)
        .join(OdfTray, OdfTray.unit_id == OdfUnit.id)
        .where(OdfTray.id == tray_id))).scalar_one_or_none()


async def room_of_cable(db: AsyncSession, cable_id: int) -> int | None:
    return (await db.execute(
        select(Cable.room_id).where(Cable.id == cable_id))).scalar_one_or_none()


# ---------------- 便捷断言 ----------------
async def assert_rack(db: AsyncSession, user: User, rack_id: int) -> None:
    await assert_room(db, user, await room_of_rack(db, rack_id))


async def assert_device(db: AsyncSession, user: User, device_id: int) -> None:
    await assert_room(db, user, await room_of_device(db, device_id))


async def assert_port(db: AsyncSession, user: User, port_id: int) -> None:
    await assert_room(db, user, await room_of_port(db, port_id))


async def assert_slot(db: AsyncSession, user: User, slot_id: int) -> None:
    await assert_room(db, user, await room_of_slot(db, slot_id))


async def assert_cabinet(db: AsyncSession, user: User, cabinet_id: int) -> None:
    await assert_room(db, user, await room_of_cabinet(db, cabinet_id))


async def assert_unit(db: AsyncSession, user: User, unit_id: int) -> None:
    await assert_room(db, user, await room_of_unit(db, unit_id))


async def assert_tray(db: AsyncSession, user: User, tray_id: int) -> None:
    await assert_room(db, user, await room_of_tray(db, tray_id))


async def assert_cable(db: AsyncSession, user: User, cable_id: int) -> None:
    await assert_room(db, user, await room_of_cable(db, cable_id))


async def assert_ports_pair(db: AsyncSession, user: User, a_id: int, b_id: int,
                            what: str = "连接") -> None:
    """两端都必须可写；跨机房连接仅核心管理员可建。"""
    scope = await user_scope(db, user)
    if scope is None:
        return
    ra = await room_of_port(db, a_id)
    rb = await room_of_port(db, b_id)
    if ra is None or rb is None:
        raise HTTPException(403, f"{what}端口所属机房无法确定，拒绝写入")
    if ra not in scope or rb not in scope:
        raise HTTPException(403, f"{what}两端必须都在你的权限范围内（跨机房{what}仅核心管理员可操作）")


async def require_core(user: User) -> None:
    if user.role != "core_admin":
        raise HTTPException(403, "该操作仅核心机房管理员可执行")
