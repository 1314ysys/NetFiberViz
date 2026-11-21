"""一次性回填：按模板默认值修正多 U 设备的 u_height（只影响仍为默认 1U 的多 U 机型）。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.api.v1.device_templates import u_height_of  # noqa: E402
from app.models import Device  # noqa: E402


async def main():
    async with SessionLocal() as db:
        devs = (await db.execute(select(Device))).scalars().all()
        changed = 0
        for d in devs:
            want = u_height_of(d.template_key or "", d.category or d.device_type or "")
            if want > 1 and (d.u_height or 1) == 1:
                print(f"{d.name}: 1U -> {want}U (template={d.template_key or '-'}, category={d.category or d.device_type})")
                d.u_height = want
                changed += 1
        await db.commit()
        print("updated:", changed, "/", len(devs))


asyncio.run(main())
