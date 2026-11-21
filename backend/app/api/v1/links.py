"""端到端链路：跨 跳纤/盘间连接/芯熔接 三类连接 BFS 求路径。"""
import json
from collections import deque

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.db import get_db
from app.models import Core, Interconnect, Link, PatchCord, Port
from app.services.audit import audit, get_port, to_dict
from app.services.perms import assert_ports_pair

router = APIRouter(prefix="/links", tags=["links"])


async def build_connection_graph(db: AsyncSession) -> dict[int, list[tuple[int, str]]]:
    """adj[port_id] = [(neighbor_port_id, edge_desc), ...]
    盘间连接：slot_a.port_id ↔ slot_b.port_id；芯熔接：core_a.port_id ↔ core_b.port_id（虚拟边）。"""
    adj: dict[int, list[tuple[int, str]]] = {}
    for cord in (await db.execute(select(PatchCord).where(PatchCord.status == "active"))).scalars():
        adj.setdefault(cord.port_a_id, []).append((cord.port_b_id, f"跳纤#{cord.id}"))
        adj.setdefault(cord.port_b_id, []).append((cord.port_a_id, f"跳纤#{cord.id}"))
    slots = (await db.execute(select(Interconnect))).scalars().all()
    slot_ids = {s for ic in slots for s in (ic.slot_a_id, ic.slot_b_id)}
    slot_port = {}
    if slot_ids:
        from app.models import OdfSlot
        for s in (await db.execute(select(OdfSlot).where(OdfSlot.id.in_(slot_ids)))).scalars():
            slot_port[s.id] = s.port_id
    for ic in slots:
        pa, pb = slot_port.get(ic.slot_a_id), slot_port.get(ic.slot_b_id)
        if pa and pb:
            desc = "熔接" if ic.kind == "splice" else "法兰直通"
            adj.setdefault(pa, []).append((pb, f"{desc}(盘间#{ic.id})"))
            adj.setdefault(pb, []).append((pa, f"{desc}(盘间#{ic.id})"))
    cores = (await db.execute(select(Core).where(Core.peer_core_id.isnot(None)))).scalars().all()
    core_by_id = {c.id: c for c in cores}
    for c in cores:
        peer = core_by_id.get(c.peer_core_id)
        if peer and c.port_id and peer.port_id and c.id < peer.id:
            adj.setdefault(c.port_id, []).append((peer.port_id, f"芯熔接(芯#{c.core_no}↔#{peer.core_no})"))
            adj.setdefault(peer.port_id, []).append((c.port_id, f"芯熔接(芯#{c.core_no}↔#{peer.core_no})"))
    return adj


async def trace_path(db: AsyncSession, from_port: int, to_port: int) -> list[dict] | None:
    adj = await build_connection_graph(db)
    if from_port == to_port:
        return []
    prev: dict[int, tuple[int, str]] = {}
    visited = {from_port}
    q = deque([from_port])
    while q:
        cur = q.popleft()
        for nb, desc in adj.get(cur, []):
            if nb in visited:
                continue
            visited.add(nb)
            prev[nb] = (cur, desc)
            if nb == to_port:
                path = []
                node = to_port
                while node != from_port:
                    p, d = prev[node]
                    path.append({"from_port": p, "to_port": node, "via": d})
                    node = p
                return list(reversed(path))
            q.append(nb)
    return None


class LinkIn(BaseModel):
    name: str
    a_port_id: int
    z_port_id: int


@router.get("/trace")
async def trace(from_port: int, to_port: int, db: AsyncSession = Depends(get_db)):
    await get_port(db, from_port)
    await get_port(db, to_port)
    path = await trace_path(db, from_port, to_port)
    if path is None:
        raise HTTPException(404, "两端之间无可达物理路径")
    pa = await get_port(db, from_port)
    pz = await get_port(db, to_port)
    return {"a": to_dict(pa), "z": to_dict(pz), "hops": path, "hop_count": len(path)}


@router.get("")
async def list_links(db: AsyncSession = Depends(get_db)):
    return [to_dict(l) for l in (await db.execute(select(Link))).scalars()]


@router.post("")
async def create_link(body: LinkIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_port(db, body.a_port_id)
    await get_port(db, body.z_port_id)
    await assert_ports_pair(db, user, body.a_port_id, body.z_port_id, "链路")
    path = await trace_path(db, body.a_port_id, body.z_port_id)
    if path is None:
        raise HTTPException(409, "两端之间无可达物理路径，无法创建链路")
    link = Link(name=body.name, a_port_id=body.a_port_id, z_port_id=body.z_port_id,
                path_json=json.dumps(path, ensure_ascii=False))
    db.add(link)
    await db.flush()
    await audit(db, user.id, "link", link.id, "create", after=link)
    await db.commit()
    await db.refresh(link)
    return to_dict(link)
