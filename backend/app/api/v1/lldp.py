"""LLDP 邻居表导入：两段式（parse 预览 → apply 确认）。
支持 CSV / TXT（每行 local_port, neighbor_port[, neighbor_name]）与 XLSX。
端口名归一化：用户可维护映射（简单规则：去空白、常见前缀缩写归一）。"""
import csv
import io
import json
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.db import get_db
from app.core.config import settings
from app.models import PatchCord, Port, Task
from app.services.audit import audit
from app.services.perms import assert_ports_pair

router = APIRouter(prefix="/lldp", tags=["lldp"])

PREFIX_RULES = [
    (re.compile(r"^Ten-?GigabitEthernet", re.I), "XGE"),
    (re.compile(r"^GigabitEthernet", re.I), "GE"),
    (re.compile(r"^XGE", re.I), "XGE"),
    (re.compile(r"^GE", re.I), "GE"),
    (re.compile(r"^Ethernet(\d)", re.I), r"GE0/0/\1"),
]


def normalize(name: str) -> str:
    n = name.strip()
    for pat, repl in PREFIX_RULES:
        n = pat.sub(repl, n)
    return n.replace(" ", "").upper()


async def parse_file(content: bytes, filename: str) -> list[dict]:
    pairs: list[dict] = []
    if filename.lower().endswith((".xlsx",)):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            if not row or not row[0]:
                continue
            vals = [str(v) for v in row if v is not None]
            if len(vals) >= 2 and not vals[0].lower().startswith(("local", "端口", "interface")):
                pairs.append({"local_port": vals[0], "neighbor_port": vals[1],
                              "neighbor_name": vals[2] if len(vals) > 2 else ""})
    elif filename.lower().endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        for row in csv.reader(io.StringIO(text)):
            if len(row) >= 2 and not row[0].lower().startswith(("local", "端口", "interface")):
                pairs.append({"local_port": row[0].strip(), "neighbor_port": row[1].strip(),
                              "neighbor_name": row[2].strip() if len(row) > 2 else ""})
    else:  # txt：逗号/制表符分隔
        text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
        for line in text.splitlines():
            if not line.strip():
                continue
            parts = re.split(r"[,\t]+", line.strip())
            if len(parts) >= 2 and not parts[0].lower().startswith(("local", "端口", "interface")):
                pairs.append({"local_port": parts[0].strip(), "neighbor_port": parts[1].strip(),
                              "neighbor_name": parts[2].strip() if len(parts) > 2 else ""})
    return pairs


@router.post("/import")
async def lldp_import(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)):
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, f"文件过大，上限 {settings.max_upload_bytes // (1024 * 1024)} MB")
    if not content:
        raise HTTPException(400, "空文件")
    pairs = await parse_file(content, file.filename or "lldp.txt")
    if not pairs:
        raise HTTPException(400, "未解析到任何邻居对（需要每行: 本端端口,对端端口[,对端设备名]）")
    # 匹配
    all_ports = (await db.execute(select(Port))).scalars().all()
    by_no: dict[str, Port] = {}
    for p in all_ports:
        by_no.setdefault(normalize(p.port_no), p)
    active_cords = (await db.execute(select(PatchCord).where(PatchCord.status == "active"))).scalars().all()
    cord_pairs = {(min(c.port_a_id, c.port_b_id), max(c.port_a_id, c.port_b_id)) for c in active_cords}

    match, missing, conflict = [], [], []
    for pr in pairs:
        la, lb = normalize(pr["local_port"]), normalize(pr["neighbor_port"])
        pa, pb = by_no.get(la), by_no.get(lb)
        if not pa or not pb:
            missing.append({**pr, "reason": f"端口不存在: {'' if pa else la} {'' if pb else lb}".strip()})
            continue
        key = (min(pa.id, pb.id), max(pa.id, pb.id))
        if key in cord_pairs:
            match.append(pr)
        else:
            conflict.append({**pr, "port_a_id": pa.id, "port_b_id": pb.id,
                             "reason": "系统无此跳纤（可应用生成）"})
    report = {"total": len(pairs), "match": match, "missing": missing,
              "conflict": conflict, "filename": file.filename}
    db.add(Task(kind="lldp_parse", payload_json=report, status="done"))
    await db.commit()
    return report


class ApplyIn(BaseModel):
    conflict: list[dict]  # 从预览报告中确认的 conflict 项


@router.post("/apply")
async def lldp_apply(body: ApplyIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    created = []
    for item in body.conflict:
        pa_id, pb_id = item.get("port_a_id"), item.get("port_b_id")
        if not pa_id or not pb_id:
            continue
        # 权限：两端都必须在作用域内（跨机房自动布线仅核心管理员）
        await assert_ports_pair(db, user, pa_id, pb_id, "跳纤")
        # 跳过端口已被占用的
        q = select(PatchCord).where(PatchCord.status == "active",
                                    (PatchCord.port_a_id.in_([pa_id, pb_id])) |
                                    (PatchCord.port_b_id.in_([pa_id, pb_id])))
        if (await db.execute(q)).scalar_one_or_none():
            continue
        cord = PatchCord(port_a_id=pa_id, port_b_id=pb_id, cord_type="LLDP 自动生成", created_by=user.id)
        db.add(cord)
        await db.flush()
        for pid in (pa_id, pb_id):
            port = (await db.execute(select(Port).where(Port.id == pid))).scalar_one_or_none()
            if port:
                port.status = "used"
        await audit(db, user.id, "patch_cord", cord.id, "create", after=cord, remark="LLDP 自动布线")
        created.append({"port_a_id": pa_id, "port_b_id": pb_id})
    await db.commit()
    return {"created": created, "count": len(created)}
