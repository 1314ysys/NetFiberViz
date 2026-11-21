"""服务层：所有写操作的唯一入口，自动写 ChangeLog + 连接唯一性校验。"""
import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ChangeLog
from app.models.connection import Interconnect, PatchCord
from app.models.resource import Port


def to_dict(obj: Any) -> dict:
    out = {}
    for c in obj.__table__.columns:
        if c.name == "password_hash":
            continue
        v = getattr(obj, c.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        out[c.name] = v
    return out


async def audit(db: AsyncSession, user_id: int, entity_type: str, entity_id: int,
                action: str, before: Any = None, after: Any = None, remark: str = "") -> None:
    db.add(ChangeLog(
        user_id=user_id, entity_type=entity_type, entity_id=entity_id, action=action,
        before_json=to_dict(before) if hasattr(before, "__table__") else before,
        after_json=to_dict(after) if hasattr(after, "__table__") else after,
        remark=remark,
    ))


async def get_port(db: AsyncSession, port_id: int) -> Port:
    port = (await db.execute(select(Port).where(Port.id == port_id))).scalar_one_or_none()
    if not port:
        raise HTTPException(404, f"端口 {port_id} 不存在")
    return port


async def ensure_port_free_for_cord(db: AsyncSession, port_id: int, cord_id: int | None = None) -> None:
    """一端口一在用跳纤（DB+service 双重校验的 service 侧）。"""
    q = select(PatchCord).where(PatchCord.status == "active").where(
        (PatchCord.port_a_id == port_id) | (PatchCord.port_b_id == port_id))
    if cord_id:
        q = q.where(PatchCord.id != cord_id)
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"端口 {port_id} 已有在用跳纤 #{existing.id}")


async def ensure_slot_free_for_interconnect(db: AsyncSession, slot_id: int, ic_id: int | None = None) -> None:
    q = select(Interconnect).where(
        (Interconnect.slot_a_id == slot_id) | (Interconnect.slot_b_id == slot_id))
    if ic_id:
        q = q.where(Interconnect.id != ic_id)
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"ODF 孔位 {slot_id} 已有盘间连接 #{existing.id}")
