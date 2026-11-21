"""演示种子数据：python scripts/seed_demo.py [--db url]"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (Base, Cable, Core, Device, Interconnect, OdfCabinet,  # noqa: E402
                        OdfSlot, OdfTray, OdfUnit, PatchCord, Port, Rack, Room, User,
                        UserRoom)


async def main():
    from app.api.v1.device_templates import TEMPLATE_BY_KEY, build_ports, u_height_of
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        if (await db.execute(select(func.count(User.id)))).scalar() == 0:
            db.add(User(username="admin", password_hash=hash_password("admin1234"),
                        display_name="演示管理员", role="core_admin"))
            await db.flush()

        if (await db.execute(select(func.count(Room.id)))).scalar():
            print("已有数据，跳过种子")
            await db.commit()
            return

        room = Room(name="核心机房", code="CR-01", address="A栋2楼")
        db.add(room); await db.flush()

        # 层级：核心机房 → 前端机房
        site_room = Room(name="一号前端机房", code="FR-01", address="B栋1楼", parent_id=room.id)
        db.add(site_room); await db.flush()

        # 演示站点管理员（仅授权前端机房）
        site_user = User(username="site01", password_hash=hash_password("site12345"),
                         display_name="前端机房管理员", role="site_admin")
        db.add(site_user); await db.flush()
        db.add(UserRoom(user_id=site_user.id, room_id=site_room.id))

        rack1 = Rack(room_id=room.id, name="01架", code="R01", pos_x=40, pos_y=60)
        rack2 = Rack(room_id=room.id, name="02架", code="R02", pos_x=320, pos_y=60)
        db.add_all([rack1, rack2]); await db.flush()

        agg = Device(rack_id=rack1.id, name="汇聚交换机-01", model="S5730", device_type="sw",
                     category="sw", template_key="sw-24ge-4sfp",
                     u_height=u_height_of("sw-24ge-4sfp", "sw"))
        olt = Device(rack_id=rack2.id, name="OLT-01", model="C600", device_type="olt",
                     category="olt", template_key="olt-16pon",
                     u_height=u_height_of("olt-16pon", "olt"))
        mc = Device(rack_id=rack2.id, name="收发器-01", device_type="media_conv",
                    category="media_conv", template_key="mc-1",
                    u_height=u_height_of("mc-1", "media_conv"))
        db.add_all([agg, olt, mc]); await db.flush()

        def ports_of(dev):
            return None  # 端口统一走 dev_ports

        # 设备端口（按模板端口组生成，分组成排）
        dev_ports: dict[int, dict[str, Port]] = {agg.id: {}, olt.id: {}, mc.id: {}}
        for dev in (agg, olt, mc):
            tpl = TEMPLATE_BY_KEY.get(dev.template_key)
            groups = tpl["groups"] if tpl else []
            for p in build_ports(groups):
                port = Port(owner_type="device", owner_id=dev.id, **p)
                db.add(port); await db.flush()
                dev_ports[dev.id][port.port_no] = port

        # ODF：1柜 3单元(A/B/C) 各2盘(1x12)
        cab = OdfCabinet(room_id=room.id, name="ODF-1", code="ODF01", pos_x=600, pos_y=60)
        db.add(cab); await db.flush()
        unit_names = ["A", "B", "C"]
        slot_map: dict[str, Port] = {}
        for ui, un in enumerate(unit_names, 1):
            unit = OdfUnit(cabinet_id=cab.id, name=un, seq=ui,
                           pos_x=60 + (ui - 1) * 340, pos_y=60)
            db.add(unit); await db.flush()
            for ti in (1, 2):
                tray = OdfTray(unit_id=unit.id, name=str(ti), seq=ti,
                               pos_x=60 + (ui - 1) * 340, pos_y=60 + (ti - 1) * 56)
                db.add(tray); await db.flush()
                for c in range(1, 13):
                    p = Port(owner_type="odf_slot", owner_id=0, port_no=f"{un}{c}")
                    db.add(p); await db.flush()
                    slot = OdfSlot(tray_id=tray.id, row_label="", col_no=c, port_id=p.id)
                    db.add(slot); await db.flush()
                    p.owner_id = slot.id
                    slot_map[f"{un}{ti}-{c}"] = p

        S = slot_map
        async def cord(a: Port, b: Port, remark=""):
            c = PatchCord(port_a_id=a.id, port_b_id=b.id, cord_type="LC-LC 单模", created_by=1, remark=remark)
            db.add(c); await db.flush()
            a.status = b.status = "used"

        await cord(dev_ports[agg.id]["GE0/0/1"], S["A1-1"])
        await cord(dev_ports[agg.id]["GE0/0/2"], S["A1-2"])
        await cord(dev_ports[olt.id]["GPON0/1"], S["A2-1"])
        await cord(dev_ports[mc.id]["OPT/1"], S["B1-1"])

        # 盘间连接：A1盘3↔4 法兰直通
        sa = (await db.execute(select(OdfSlot).where(OdfSlot.port_id == S["A1-3"].id))).scalar_one()
        sb = (await db.execute(select(OdfSlot).where(OdfSlot.port_id == S["A1-4"].id))).scalar_one()
        db.add(Interconnect(slot_a_id=sa.id, slot_b_id=sb.id, kind="adapter", created_by=1))

        # 光缆：48芯进缆，24芯成端 A2 盘，余 24 芯与对接缆熔接
        c1 = Cable(room_id=room.id, name="进局光缆-01", core_count=48, direction_from="东侧管道")
        c2 = Cable(room_id=room.id, name="对接光缆-02", core_count=24, direction_from="西南方向")
        db.add_all([c1, c2]); await db.flush()
        cores1, cores2 = [], []
        for n in range(1, 49):
            k = Core(cable_id=c1.id, core_no=n); db.add(k); await db.flush(); cores1.append(k)
        for n in range(1, 25):
            k = Core(cable_id=c2.id, core_no=n); db.add(k); await db.flush(); cores2.append(k)
        # 1..24 芯成端到 A2 盘 12 孔 + A3 盘 12 孔
        a2 = [S[f"C1-{i}"] for i in range(1, 13)] + [S[f"C2-{i}"] for i in range(1, 13)]
        for i in range(24):
            cores1[i].status = "landed"; cores1[i].port_id = a2[i].id
            a2[i].status = "used"
        # 25..48 与对接缆 1..24 熔接
        for i in range(24):
            cores1[24 + i].status = "spliced"; cores1[24 + i].peer_core_id = cores2[i].id
            cores2[i].status = "spliced"; cores2[i].peer_core_id = cores1[24 + i].id

        # 一个故障孔位演示（C 单元盘1孔5 已被纤芯成端，改用 B 单元盘2孔5）
        S["B2-5"].status = "fault"

        await db.commit()
        print("演示数据已写入：1机房/2机柜/3设备/1 ODF柜(3单元x2盘)/4跳纤/2光缆(48+24芯)/1盘间连接")


if __name__ == "__main__":
    asyncio.run(main())
