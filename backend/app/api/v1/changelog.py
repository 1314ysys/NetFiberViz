"""变更历史查询。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models import ChangeLog

router = APIRouter(prefix="/changelog", tags=["changelog"])


@router.get("")
async def list_changes(
    entity_type: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(ChangeLog).order_by(ChangeLog.ts.desc())
    if entity_type:
        q = q.where(ChangeLog.entity_type == entity_type)
    if entity_id:
        q = q.where(ChangeLog.entity_id == entity_id)
    if user_id:
        q = q.where(ChangeLog.user_id == user_id)
    if since:
        q = q.where(ChangeLog.ts >= since)
    if until:
        q = q.where(ChangeLog.ts <= until)
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()
    return [{
        "id": c.id, "user_id": c.user_id, "ts": c.ts.isoformat(),
        "entity_type": c.entity_type, "entity_id": c.entity_id, "action": c.action,
        "before": c.before_json, "after": c.after_json, "remark": c.remark,
    } for c in rows]
