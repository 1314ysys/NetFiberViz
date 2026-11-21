"""跳纤 patch_cords：创建/删除即台账+审计；一端口一在用跳纤。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.db import get_db
from app.models import PatchCord, Port
from app.services.audit import audit, ensure_port_free_for_cord, get_port, to_dict
from app.services.perms import assert_ports_pair
from app.services.port_types import check_compatibility

router = APIRouter(prefix="/patch-cords", tags=["patch-cords"])


class CordIn(BaseModel):
    port_a_id: int
    port_b_id: int
    cord_type: str = "LC-LC 单模"
    length_m: float = 0
    remark: str = ""
    force: bool = False        # 类型不匹配时强制确认


@router.get("")
async def list_cords(db: AsyncSession = Depends(get_db)):
    return [to_dict(c) for c in (await db.execute(select(PatchCord).where(PatchCord.status == "active"))).scalars()]


@router.post("")
async def create_cord(body: CordIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if body.port_a_id == body.port_b_id:
        raise HTTPException(400, "跳纤两端不能是同一端口")
    pa, pb = await get_port(db, body.port_a_id), await get_port(db, body.port_b_id)
    # 两端都必须可写；跨机房跳纤仅核心管理员
    await assert_ports_pair(db, user, pa.id, pb.id, "跳纤")

    # 端口类型兼容性：光/电互连硬拒绝，子类型不同仅警告（需 force）
    level, msg = check_compatibility(pa.port_type, pb.port_type)
    if level == "block":
        raise HTTPException(400, msg)
    if level == "warn" and not body.force:
        raise HTTPException(409, f"接口类型不匹配：{msg}。如确认使用转接跳线，请勾选强制创建。")

    await ensure_port_free_for_cord(db, pa.id)
    await ensure_port_free_for_cord(db, pb.id)
    cord = PatchCord(**body.model_dump(exclude={"force"}), created_by=user.id)
    db.add(cord)
    await db.flush()
    pa.status = pb.status = "used"
    await audit(db, user.id, "patch_cord", cord.id, "create", after=cord)
    await audit(db, user.id, "port", pa.id, "update", after=pa, remark="跳纤占用")
    await audit(db, user.id, "port", pb.id, "update", after=pb, remark="跳纤占用")
    await db.commit()
    await db.refresh(cord)
    return to_dict(cord)


@router.delete("/{cord_id}")
async def delete_cord(cord_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    cord = (await db.execute(select(PatchCord).where(PatchCord.id == cord_id))).scalar_one_or_none()
    if not cord or cord.status != "active":
        raise HTTPException(404, "跳纤不存在或已拆除")
    await assert_ports_pair(db, user, cord.port_a_id, cord.port_b_id, "跳纤")
    cord.status = "removed"
    for pid in (cord.port_a_id, cord.port_b_id):
        port = await get_port(db, pid)
        port.status = "free"
        await audit(db, user.id, "port", port.id, "update", after=port, remark="跳纤拆除释放")
    await audit(db, user.id, "patch_cord", cord.id, "update", before=cord, after=cord, remark="拆除(软删除留痕)")
    await db.commit()
    return {"ok": True}
