"""机柜 U 位占用：冲突检测与最近空位查找。

设备在机柜中占据 [u_position, u_position + u_height - 1] 区间，
同一机柜内任意两台设备的区间不得重叠。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device


def span(u_position: int, u_height: int) -> tuple[int, int]:
    """返回设备占用的 U 区间（闭区间）。"""
    u0 = max(int(u_position), 1)
    return u0, u0 + max(int(u_height), 1) - 1


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


async def rack_occupancy(db: AsyncSession, rack_id: int,
                         exclude_device_id: int | None = None) -> list[tuple[int, int, Device]]:
    """机柜内已占用区间列表（可排除某个设备以便自检）。"""
    devs = (await db.execute(select(Device).where(Device.rack_id == rack_id))).scalars().all()
    out = []
    for d in devs:
        if exclude_device_id is not None and d.id == exclude_device_id:
            continue
        out.append((*span(d.u_position, d.u_height or 1), d))
    return out


async def find_u_conflict(db: AsyncSession, rack_id: int, u_position: int, u_height: int,
                          exclude_device_id: int | None = None) -> Device | None:
    """与目标区间冲突的第一个设备；无冲突返回 None。"""
    target = span(u_position, u_height)
    for a0, a1, dev in await rack_occupancy(db, rack_id, exclude_device_id):
        if overlaps(target, (a0, a1)):
            return dev
    return None


async def find_nearest_free_slot(db: AsyncSession, rack_id: int, u_position: int,
                                 u_height: int, u_count: int,
                                 exclude_device_id: int | None = None) -> int | None:
    """从 u_position 向上下交替搜索最近的连续空位；找不到返回 None。"""
    height = max(int(u_height), 1)
    occupied = sorted((a0, a1) for a0, a1, _ in
                      await rack_occupancy(db, rack_id, exclude_device_id))

    def free_at(u: int) -> bool:
        if u < 1 or u + height - 1 > u_count:
            return False
        t = (u, u + height - 1)
        return not any(overlaps(t, (a0, a1)) for a0, a1 in occupied)

    want = max(min(int(u_position), u_count - height + 1), 1)
    if free_at(want):
        return want
    for delta in range(1, u_count + 1):
        for cand in (want + delta, want - delta):
            if free_at(cand):
                return cand
    return None
