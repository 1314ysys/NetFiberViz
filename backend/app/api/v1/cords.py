"""跳纤 patch_cords：创建/修改/拆除均写审计并刷新最后更新时间。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.db import get_db
from app.models import ChangeLog, PatchCord
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


class CordUpdateIn(BaseModel):
    cord_type: str | None = None
    length_m: float | None = None
    remark: str | None = None


def _touch(cord: PatchCord, user_id: int) -> None:
    """刷新最后更新时间与更新人。"""
    cord.updated_at = datetime.utcnow()
    cord.updated_by = user_id


@router.get("")
async def list_cords(include_removed: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(PatchCord)
    if not include_removed:
        q = q.where(PatchCord.status == "active")
    q = q.order_by(PatchCord.updated_at.desc())
    return [to_dict(c) for c in (await db.execute(q)).scalars()]


@router.get("/{cord_id}")
async def get_cord(cord_id: int, db: AsyncSession = Depends(get_db)):
    cord = (await db.execute(select(PatchCord).where(PatchCord.id == cord_id))).scalar_one_or_none()
    if not cord:
        raise HTTPException(404, "跳纤不存在")
    return to_dict(cord)


@router.get("/{cord_id}/history")
async def cord_history(cord_id: int, db: AsyncSession = Depends(get_db)):
    """该跳纤的独立更新记录（时间线，按时间正序）。"""
    cord = (await db.execute(select(PatchCord).where(PatchCord.id == cord_id))).scalar_one_or_none()
    if not cord:
        raise HTTPException(404, "跳纤不存在")

    logs = (await db.execute(
        select(ChangeLog)
        .where(ChangeLog.entity_type == "patch_cord", ChangeLog.entity_id == cord_id)
        .order_by(ChangeLog.ts.asc())
    )).scalars().all()

    timeline = []
    for lg in logs:
        after = lg.after_json or {}
        before = lg.before_json or {}
        # 计算本次变更了哪些字段，便于前端直接展示
        changed = []
        for k in ("cord_type", "length_m", "remark", "status"):
            if lg.action == "create":
                if k in after:
                    changed.append(k)
            elif lg.action == "update":
                if k in before or k in after:
                    if before.get(k) != after.get(k):
                        changed.append(k)
        timeline.append({
            "id": lg.id,
            "ts": lg.ts.isoformat(),
            "user_id": lg.user_id,
            "action": lg.action,
            "remark": lg.remark,
            "changed": changed,
            "before": before,
            "after": after,
        })

    return {
        "cord": to_dict(cord),
        "timeline": timeline,
        "created_at": cord.created_at.isoformat() if cord.created_at else None,
        "updated_at": cord.updated_at.isoformat() if cord.updated_at else None,
        "verified_at": cord.verified_at.isoformat() if cord.verified_at else None,
    }


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

    now = datetime.utcnow()
    cord = PatchCord(
        **body.model_dump(exclude={"force"}),
        created_by=user.id, created_at=now,
        updated_at=now, updated_by=user.id,
    )
    db.add(cord)
    await db.flush()
    pa.status = pb.status = "used"
    await audit(db, user.id, "patch_cord", cord.id, "create", after=cord)
    await audit(db, user.id, "port", pa.id, "update", after=pa, remark="跳纤占用")
    await audit(db, user.id, "port", pb.id, "update", after=pb, remark="跳纤占用")
    await db.commit()
    await db.refresh(cord)
    return to_dict(cord)


@router.put("/{cord_id}")
async def update_cord(cord_id: int, body: CordUpdateIn, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)):
    """修改跳纤属性（型号/长度/备注），刷新最后更新时间并留审计。"""
    cord = (await db.execute(select(PatchCord).where(PatchCord.id == cord_id))).scalar_one_or_none()
    if not cord or cord.status != "active":
        raise HTTPException(404, "跳纤不存在或已拆除")
    await assert_ports_pair(db, user, cord.port_a_id, cord.port_b_id, "跳纤")

    before = PatchCord(**to_dict(cord))
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, "没有需要更新的字段")
    for k, v in patch.items():
        setattr(cord, k, v)
    _touch(cord, user.id)
    await audit(db, user.id, "patch_cord", cord.id, "update", before=before, after=cord)
    await db.commit()
    await db.refresh(cord)
    return to_dict(cord)


@router.post("/{cord_id}/verify")
async def verify_cord(cord_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """标记该跳纤已现场复核（用于"久未复核"筛查）。"""
    cord = (await db.execute(select(PatchCord).where(PatchCord.id == cord_id))).scalar_one_or_none()
    if not cord or cord.status != "active":
        raise HTTPException(404, "跳纤不存在或已拆除")
    await assert_ports_pair(db, user, cord.port_a_id, cord.port_b_id, "跳纤")
    before = PatchCord(**to_dict(cord))
    cord.verified_at = datetime.utcnow()
    _touch(cord, user.id)
    await audit(db, user.id, "patch_cord", cord.id, "update", before=before, after=cord,
                remark="现场复核")
    await db.commit()
    return {"ok": True, "verified_at": cord.verified_at.isoformat()}


@router.delete("/{cord_id}")
async def delete_cord(cord_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    cord = (await db.execute(select(PatchCord).where(PatchCord.id == cord_id))).scalar_one_or_none()
    if not cord or cord.status != "active":
        raise HTTPException(404, "跳纤不存在或已拆除")
    await assert_ports_pair(db, user, cord.port_a_id, cord.port_b_id, "跳纤")
    before = PatchCord(**to_dict(cord))
    cord.status = "removed"
    _touch(cord, user.id)
    for pid in (cord.port_a_id, cord.port_b_id):
        port = await get_port(db, pid)
        port.status = "free"
        await audit(db, user.id, "port", port.id, "update", after=port, remark="跳纤拆除释放")
    await audit(db, user.id, "patch_cord", cord.id, "update", before=before, after=cord,
                remark="拆除(软删除留痕)")
    await db.commit()
    return {"ok": True}
